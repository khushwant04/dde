"""Extraction provider adapters."""

from dde.providers.base import ExtractionProvider
from dde.providers.fake import FakeProvider
from dde.providers.openai_responses import OpenAIResponsesProvider

__all__ = ["ExtractionProvider", "FakeProvider", "OpenAIResponsesProvider"]
