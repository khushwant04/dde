"""Bounded load -> extract -> validate application service."""

from pathlib import Path

from dde.config import Settings
from dde.loaders import LoadedDocument, load_document
from dde.models import ResultEnvelope, SourceMetadata
from dde.providers.base import ExtractionProvider
from dde.validation import validate_document


class ExtractionPipeline:
    def __init__(self, settings: Settings, provider: ExtractionProvider) -> None:
        self._settings = settings
        self._provider = provider

    def run(self, path: Path) -> ResultEnvelope:
        loaded = load_document(path, self._settings)
        return self.run_loaded(loaded)

    def run_loaded(self, loaded: LoadedDocument) -> ResultEnvelope:
        extracted = self._provider.extract(loaded)
        source = SourceMetadata(
            file_name=loaded.file_name,
            media_type=loaded.media_type,
            byte_count=loaded.byte_count,
            page_count=loaded.page_count,
            sheet_count=loaded.sheet_count,
            sha256=loaded.sha256,
            notices=list(loaded.notices),
        )
        return ResultEnvelope(
            source=source,
            document=extracted,
            validation=validate_document(extracted, loader_notices=loaded.notices),
        )
