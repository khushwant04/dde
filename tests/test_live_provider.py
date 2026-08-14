"""Explicitly opt-in live provider verification; never runs in the offline suite by default."""

import os
from pathlib import Path

import pytest

from dde.config import Settings
from dde.pipeline import ExtractionPipeline
from dde.providers.openai_responses import OpenAIResponsesProvider

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.getenv("DDE_RUN_LIVE") != "1", reason="set DDE_RUN_LIVE=1 explicitly")
def test_live_azure_sample_returns_schema_valid_envelope() -> None:
    settings = Settings(_env_file=None)
    provider = OpenAIResponsesProvider(settings)
    sample = Path(__file__).resolve().parents[1] / "samples/documents/invoice_a.pdf"
    result = ExtractionPipeline(settings, provider).run(sample)
    assert result.schema_version == "2.0"
    assert result.source.file_name == "invoice_a.pdf"
