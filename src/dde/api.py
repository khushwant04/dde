"""Bounded synchronous HTTP transport for the extraction pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Lock
from typing import Annotated, Literal

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dde.config import Settings
from dde.errors import (
    DDEError,
    InputError,
    InputLimitError,
    ProviderConfigurationError,
    ProviderError,
    SchemaOutputError,
    UnsupportedInputError,
)
from dde.loaders.base import safe_filename
from dde.models import ResultEnvelope
from dde.pipeline import ExtractionPipeline
from dde.providers import OpenAIResponsesProvider

PipelineFactory = Callable[[], ExtractionPipeline]
Reservation = Literal["accepted", "not_accepting", "full"]


class RequestBodyLimitMiddleware:
    """Buffer at most one configured request body before framework parsing."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(chunk) > self._max_bytes - len(body):
                response = _error_response(
                    413,
                    "request_too_large",
                    "Request body exceeds the configured receive limit",
                )
                await response(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self._app(scope, replay, send)


class ExtractionService:
    """Own bounded worker capacity and uploaded-file lifetime."""

    def __init__(
        self,
        settings: Settings,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self.settings = settings
        self._custom_pipeline = pipeline_factory is not None
        self._pipeline_factory = pipeline_factory or self._openai_pipeline
        self._slots = BoundedSemaphore(settings.max_concurrent_requests)
        self._lock = Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._accepting = False

    def _openai_pipeline(self) -> ExtractionPipeline:
        return ExtractionPipeline(self.settings, OpenAIResponsesProvider(self.settings))

    def start(self) -> None:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.settings.max_concurrent_requests,
                    thread_name_prefix="dde-api",
                )
            self._accepting = True

    def shutdown(self) -> None:
        with self._lock:
            self._accepting = False
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)

    @property
    def accepting(self) -> bool:
        with self._lock:
            return self._accepting

    def configuration_ready(self) -> bool:
        if self._custom_pipeline:
            return True
        try:
            self.settings.require_provider()
        except ProviderConfigurationError:
            return False
        return True

    def try_reserve(self) -> Reservation:
        with self._lock:
            if not self._accepting or self._executor is None:
                return "not_accepting"
            if not self._slots.acquire(blocking=False):
                return "full"
            return "accepted"

    def release(self) -> None:
        self._slots.release()

    def submit(
        self,
        workspace: TemporaryDirectory[str],
        path: Path,
    ) -> Future[ResultEnvelope] | None:
        with self._lock:
            executor = self._executor if self._accepting else None
            if executor is None:
                return None
            return executor.submit(self._run, workspace, path)

    def _run(
        self,
        workspace: TemporaryDirectory[str],
        path: Path,
    ) -> ResultEnvelope:
        try:
            return self._pipeline_factory().run(path)
        finally:
            workspace.cleanup()
            self.release()


def _safe_upload_name(filename: str | None) -> str:
    candidate = (filename or "document").replace("\x00", "").replace("\\", "/")
    name = candidate.rsplit("/", 1)[-1].strip()
    return "document" if name in {"", ".", ".."} else safe_filename(Path(name))


def _stage_upload(
    upload: UploadFile,
    settings: Settings,
    temp_root: Path | None,
) -> tuple[TemporaryDirectory[str], Path]:
    workspace = TemporaryDirectory(prefix="dde-upload-", dir=temp_root)
    workspace_path = Path(workspace.name).resolve()
    path = (workspace_path / _safe_upload_name(upload.filename)).resolve()
    if path.parent != workspace_path:
        workspace.cleanup()
        raise InputError("Uploaded filename is invalid")
    byte_count = 0
    try:
        with path.open("xb") as destination:
            while chunk := upload.file.read(64 * 1024):
                byte_count += len(chunk)
                if byte_count > settings.max_file_bytes:
                    raise InputLimitError(
                        f"Upload exceeds the {settings.max_file_bytes}-byte file limit"
                    )
                destination.write(chunk)
        if byte_count == 0:
            raise InputError("Uploaded file is empty")
    except Exception:
        workspace.cleanup()
        raise
    return workspace, path


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _domain_error_response(error: DDEError) -> JSONResponse:
    if isinstance(error, InputLimitError):
        return _error_response(413, "input_limit", "Uploaded document exceeds a configured limit")
    if isinstance(error, UnsupportedInputError):
        return _error_response(415, "unsupported_input", "Uploaded document type is unsupported")
    if isinstance(error, InputError):
        return _error_response(400, "invalid_input", "Uploaded document is invalid")
    if isinstance(error, ProviderConfigurationError):
        return _error_response(503, "provider_unavailable", "Provider configuration is unavailable")
    if isinstance(error, ProviderError):
        return _error_response(502, "provider_error", "Document provider request failed")
    if isinstance(error, SchemaOutputError):
        return _error_response(
            502, "schema_output_error", "Provider output did not match the schema"
        )
    return _error_response(500, "internal_error", "Extraction failed")


def create_app(
    settings: Settings | None = None,
    pipeline_factory: PipelineFactory | None = None,
    temp_root: Path | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    service = ExtractionService(resolved_settings, pipeline_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        service.start()
        try:
            yield
        finally:
            await asyncio.to_thread(service.shutdown)

    application = FastAPI(title="Document Data Extractor", version="2.0", lifespan=lifespan)
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=resolved_settings.max_request_bytes,
    )
    application.state.extraction_service = service

    @application.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz", response_model=None)
    def readiness() -> JSONResponse | dict[str, str]:
        if service.accepting and service.configuration_ready():
            return {"status": "ready"}
        return _error_response(503, "not_ready", "Service is not ready for extraction")

    @application.post("/v1/extractions", response_model=ResultEnvelope)
    def extract(file: Annotated[UploadFile, File(...)]) -> ResultEnvelope | JSONResponse:
        reservation = service.try_reserve()
        if reservation == "not_accepting":
            return _error_response(503, "not_ready", "Service is not accepting extraction work")
        if reservation == "full":
            return _error_response(429, "busy", "Extraction concurrency limit is reached")

        workspace: TemporaryDirectory[str] | None = None
        submitted = False
        try:
            workspace, path = _stage_upload(file, resolved_settings, temp_root)
            future = service.submit(workspace, path)
            if future is None:
                return _error_response(503, "not_ready", "Service is shutting down")
            submitted = True
            try:
                return future.result(timeout=resolved_settings.api_timeout_seconds)
            except FutureTimeoutError:
                return _error_response(504, "deadline_exceeded", "Extraction deadline exceeded")
            except DDEError as exc:
                return _domain_error_response(exc)
            except Exception:
                return _error_response(500, "internal_error", "Extraction failed")
        except DDEError as exc:
            return _domain_error_response(exc)
        except OSError:
            return _error_response(500, "temporary_storage_error", "Temporary storage failed")
        finally:
            file.file.close()
            if not submitted:
                if workspace is not None:
                    workspace.cleanup()
                service.release()

    return application


app = create_app()
