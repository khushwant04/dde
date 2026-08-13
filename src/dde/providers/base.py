"""Provider port for one bounded extraction operation."""

from typing import Protocol

from dde.loaders import LoadedDocument
from dde.models import ExtractedDocument


class ExtractionProvider(Protocol):
    def extract(self, document: LoadedDocument) -> ExtractedDocument:
        """Extract only model-owned document fields from canonical content."""
        ...
