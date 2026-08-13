"""Deterministic provider used only for offline tests and fixture smoke runs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from dde.errors import ProviderRequestError, SchemaOutputError
from dde.loaders import LoadedDocument
from dde.models import ExtractedDocument


class FakeProvider:
    def __init__(
        self,
        responses: Mapping[str, ExtractedDocument] | None = None,
        fixture_dir: Path | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._fixture_dir = fixture_dir
        self._failure = failure
        self.calls = 0

    def extract(self, document: LoadedDocument) -> ExtractedDocument:
        self.calls += 1
        if self._failure:
            raise self._failure
        response = self._responses.get(document.file_name)
        if response is not None:
            return response.model_copy(deep=True)
        if self._fixture_dir is not None:
            path = self._fixture_dir / f"{Path(document.file_name).stem}.json"
            if path.is_file():
                try:
                    return ExtractedDocument.model_validate_json(path.read_text())
                except (ValueError, OSError) as exc:
                    raise SchemaOutputError(f"Invalid fake response: {path.name}") from exc
        raise ProviderRequestError(
            f"No fake response for {document.file_name}; fake mode is fixture-only"
        )
