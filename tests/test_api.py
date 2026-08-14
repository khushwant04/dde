from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import pytest
from fastapi.testclient import TestClient

from dde.api import RequestBodyLimitMiddleware, _safe_upload_name, create_app
from dde.config import Settings
from dde.errors import ProviderConfigurationError, ProviderRequestError, SchemaOutputError
from dde.loaders import LoadedDocument
from dde.models import ExtractedDocument
from dde.pipeline import ExtractionPipeline
from dde.providers.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
INVOICE_C_BYTES = (SAMPLES / "documents/invoice_c.txt").read_bytes()
INVOICE_C = ExtractedDocument.model_validate_json(
    (SAMPLES / "fake_responses/invoice_c.json").read_text()
)


def api_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DDE_MAX_FILE_BYTES": 1_000_000,
        "DDE_MAX_REQUEST_BYTES": 1_100_000,
        "DDE_MAX_CONCURRENT_REQUESTS": 2,
        "DDE_API_TIMEOUT_SECONDS": 2.0,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def fake_client(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    provider: FakeProvider | None = None,
) -> tuple[TestClient, FakeProvider]:
    resolved_settings = settings or api_settings()
    resolved_provider = provider or FakeProvider(fixture_dir=SAMPLES / "fake_responses")
    application = create_app(
        resolved_settings,
        pipeline_factory=lambda: ExtractionPipeline(resolved_settings, resolved_provider),
        temp_root=tmp_path,
    )
    return TestClient(application), resolved_provider


def upload(
    client: TestClient,
    data: bytes = INVOICE_C_BYTES,
    filename: str = "invoice_c.txt",
) -> object:
    return client.post(
        "/v1/extractions",
        files={"file": (filename, data, "application/octet-stream")},
    )


def test_health_and_readiness_are_offline_and_shutdown_stops_accepting(tmp_path: Path) -> None:
    client, provider = fake_client(tmp_path)
    service = client.app.state.extraction_service
    with client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").json() == {"status": "ready"}
        assert provider.calls == 0
        assert service.accepting is True
    assert service.accepting is False


def test_readiness_reports_missing_provider_configuration_without_network() -> None:
    settings = Settings.model_validate(
        {
            "OPENAI_BASE_URL": None,
            "OPENAI_API_KEY": None,
            "DDE_MODEL": None,
            "DDE_AUTH_MODE": "api_key",
        }
    )
    application = create_app(settings)
    with TestClient(application) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"


@pytest.mark.parametrize("unsafe_name", ["../../invoice_c.txt", "..\\..\\invoice_c.txt"])
def test_multipart_extraction_sanitizes_filename_and_cleans_workspace(
    tmp_path: Path, unsafe_name: str
) -> None:
    client, provider = fake_client(tmp_path)
    with client:
        response = upload(client, filename=unsafe_name)
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "2.0"
    assert payload["source"]["file_name"] == "invoice_c.txt"
    assert payload["document"]["document_id"] is None
    assert provider.calls == 1
    assert list(tmp_path.iterdir()) == []


def test_receive_limit_rejects_before_multipart_or_provider(tmp_path: Path) -> None:
    settings = api_settings(DDE_MAX_REQUEST_BYTES=128)
    client, provider = fake_client(tmp_path, settings=settings)
    with client:
        response = upload(client, data=b"x" * 512)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []


def test_file_limit_and_empty_upload_are_rejected_and_cleaned(tmp_path: Path) -> None:
    settings = api_settings(DDE_MAX_FILE_BYTES=4, DDE_MAX_REQUEST_BYTES=10_000)
    client, provider = fake_client(tmp_path, settings=settings)
    with client:
        oversized = upload(client, data=b"12345")
        empty = upload(client, data=b"")
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "input_limit"
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "invalid_input"
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []


def test_unsupported_input_is_sanitized_and_skips_provider(tmp_path: Path) -> None:
    client, provider = fake_client(tmp_path)
    with client:
        response = upload(client, data=b"not a supported document", filename="payload.bin")
    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "unsupported_input",
            "message": "Uploaded document type is unsupported",
        }
    }
    assert provider.calls == 0
    assert str(tmp_path) not in response.text
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (ProviderConfigurationError("secret config detail"), 503, "provider_unavailable"),
        (ProviderRequestError("secret provider payload"), 502, "provider_error"),
        (SchemaOutputError("secret schema payload"), 502, "schema_output_error"),
        (RuntimeError("secret stack detail"), 500, "internal_error"),
    ],
)
def test_provider_and_internal_errors_are_sanitized(
    tmp_path: Path,
    failure: Exception,
    status: int,
    code: str,
) -> None:
    provider = FakeProvider(failure=failure)
    client, _ = fake_client(tmp_path, provider=provider)
    with client:
        response = upload(client)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "secret" not in response.text
    assert str(tmp_path) not in response.text
    assert list(tmp_path.iterdir()) == []


class BlockingProvider:
    def __init__(self, *, block_once: bool = False) -> None:
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self._calls = 0
        self._block_once = block_once

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def extract(self, document: LoadedDocument) -> ExtractedDocument:
        del document
        with self._lock:
            self._calls += 1
            call_number = self._calls
        if not self._block_once or call_number == 1:
            self.started.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("test release timeout")
        return INVOICE_C.model_copy(deep=True)


def test_concurrency_limit_rejects_new_work_without_queueing(tmp_path: Path) -> None:
    settings = api_settings(DDE_MAX_CONCURRENT_REQUESTS=1)
    provider = BlockingProvider()
    application = create_app(
        settings,
        pipeline_factory=lambda: ExtractionPipeline(settings, provider),
        temp_root=tmp_path,
    )
    with TestClient(application) as client, ThreadPoolExecutor(max_workers=1) as requests:
        first = requests.submit(upload, client)
        assert provider.started.wait(timeout=2)
        second = upload(client)
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "busy"
        assert provider.calls == 1
        provider.release.set()
        assert first.result(timeout=2).status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_deadline_keeps_slot_and_workspace_until_worker_finishes(tmp_path: Path) -> None:
    settings = api_settings(
        DDE_MAX_CONCURRENT_REQUESTS=1,
        DDE_API_TIMEOUT_SECONDS=0.02,
    )
    provider = BlockingProvider(block_once=True)
    application = create_app(
        settings,
        pipeline_factory=lambda: ExtractionPipeline(settings, provider),
        temp_root=tmp_path,
    )
    with TestClient(application) as client:
        timed_out = upload(client)
        assert timed_out.status_code == 504
        assert timed_out.json()["error"]["code"] == "deadline_exceeded"
        assert provider.started.is_set()
        assert list(tmp_path.iterdir())

        overloaded = upload(client)
        assert overloaded.status_code == 429
        provider.release.set()
        deadline = time.monotonic() + 2
        while list(tmp_path.iterdir()) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert list(tmp_path.iterdir()) == []

        recovered = upload(client)
        assert recovered.status_code == 200
    assert provider.calls == 2


def test_api_result_is_strict_result_envelope(tmp_path: Path) -> None:
    client, _ = fake_client(tmp_path)
    with client:
        response = upload(client)
    parsed = json.loads(response.text)
    assert parsed["validation"]["review_required"] is True
    assert parsed["validation"]["issues"][0]["code"] == "MISSING_IDENTIFIER"


def test_receive_limit_counts_chunks_without_trusting_content_length() -> None:
    async def exercise(
        chunks: list[bytes], max_bytes: int, headers: list[tuple[bytes, bytes]]
    ) -> tuple[bool, bytes, int]:
        downstream_called = False
        downstream_body = bytearray()
        messages = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            return messages.pop(0)

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        async def downstream(
            scope: dict[str, object],
            receive_body: object,
            send_response: object,
        ) -> None:
            del scope, send_response
            nonlocal downstream_called
            downstream_called = True
            receiver = receive_body
            while True:
                message = await receiver()  # type: ignore[operator]
                downstream_body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/extractions",
            "raw_path": b"/v1/extractions",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
        middleware = RequestBodyLimitMiddleware(downstream, max_bytes)  # type: ignore[arg-type]
        await middleware(scope, receive, send)  # type: ignore[arg-type]
        status = (
            next(
                int(message["status"])
                for message in sent
                if message.get("type") == "http.response.start"
            )
            if sent
            else 200
        )
        return downstream_called, bytes(downstream_body), status

    exact = asyncio.run(exercise([b"ab", b"cd"], 4, []))
    assert exact == (True, b"abcd", 200)
    fragmented = asyncio.run(exercise([b"ab", b"cde"], 4, [(b"content-length", b"1")]))
    assert fragmented == (False, b"", 413)
    single_large = asyncio.run(exercise([b"x" * 5_000_000], 1_024, []))
    assert single_large == (False, b"", 413)


@pytest.mark.parametrize("unsafe_name", ["..", "../..", "..\\..", ".\x00.", ".", ""])
def test_dot_only_and_nul_upload_names_are_normalized(unsafe_name: str) -> None:
    assert _safe_upload_name(unsafe_name) == "document"


def test_shutdown_race_explicitly_cleans_workspace_and_releases_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = fake_client(tmp_path)
    service = client.app.state.extraction_service
    with client:
        monkeypatch.setattr(service, "submit", lambda workspace, path: None)
        response = upload(client)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_ready"
        assert list(tmp_path.iterdir()) == []
        assert service.try_reserve() == "accepted"
        service.release()


def test_malformed_multipart_and_temp_storage_failures_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, provider = fake_client(tmp_path)
    with client:
        malformed = client.post(
            "/v1/extractions",
            content=b"not multipart",
            headers={"content-type": "multipart/form-data; boundary=missing"},
        )
        assert malformed.status_code in {400, 422}
        assert str(tmp_path) not in malformed.text

        def fail_workspace(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise OSError("secret temporary path")

        monkeypatch.setattr("dde.api.TemporaryDirectory", fail_workspace)
        storage_failure = upload(client)
    assert storage_failure.status_code == 500
    assert storage_failure.json()["error"]["code"] == "temporary_storage_error"
    assert "secret" not in storage_failure.text
    assert str(tmp_path) not in storage_failure.text
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []
