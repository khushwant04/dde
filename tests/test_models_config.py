from __future__ import annotations

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dde.config import Settings
from dde.errors import (
    DDEError,
    ExitCode,
    InputError,
    ProviderConfigurationError,
    ProviderError,
    SchemaOutputError,
)
from dde.models import ExtractedDocument, ResultEnvelope


def document_json() -> dict[str, object]:
    return {
        "document_type": "invoice",
        "document_id": None,
        "vendor": {"name": "Vendor", "tax_id": None, "address": None},
        "customer_name": None,
        "issue_date": None,
        "due_date": None,
        "currency": "USD",
        "line_items": [],
        "subtotal": "10.00",
        "discount": None,
        "tax": None,
        "shipping": None,
        "total": "10.00",
    }


def test_provider_money_schema_uses_strings_not_numbers() -> None:
    schema = ExtractedDocument.model_json_schema()
    total_types = {item["type"] for item in schema["properties"]["total"]["anyOf"]}
    line_types = {
        item["type"] for item in schema["$defs"]["LineItem"]["properties"]["amount"]["anyOf"]
    }
    assert total_types == {"string", "null"}
    assert line_types == {"string", "null"}


def test_provider_schema_requires_all_fields_and_forbids_unknowns() -> None:
    schema = ExtractedDocument.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])


def test_decimal_strings_parse_and_serialize_without_float() -> None:
    document = ExtractedDocument.model_validate_json(json.dumps(document_json()))
    assert document.total == Decimal("10.00")
    assert json.loads(document.model_dump_json())["total"] == "10.00"


@pytest.mark.parametrize("invalid", ["1e2", "1E+2", "+10.00", "01.00", ".5", "NaN", "Infinity"])
def test_non_plain_decimal_strings_are_rejected(invalid: str) -> None:
    payload = document_json()
    payload["total"] = invalid
    with pytest.raises(ValidationError):
        ExtractedDocument.model_validate_json(json.dumps(payload))


def test_unknown_fields_and_missing_nullable_fields_are_rejected() -> None:
    payload = document_json()
    payload["invented"] = True
    with pytest.raises(ValidationError):
        ExtractedDocument.model_validate_json(json.dumps(payload))
    payload = document_json()
    del payload["due_date"]
    with pytest.raises(ValidationError):
        ExtractedDocument.model_validate_json(json.dumps(payload))


def test_result_rejects_model_only_document_as_envelope() -> None:
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate_json(json.dumps(document_json()))


def test_settings_aliases_limits_and_secret_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/openai/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-value")
    monkeypatch.setenv("DDE_MODEL", "deployment")
    monkeypatch.setenv("DDE_MAX_PAGES", "3")
    settings = Settings(_env_file=None)
    settings.require_provider()
    assert settings.max_pages == 3
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in json.dumps(settings.safe_summary())


def test_settings_support_azure_identity_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/openai/v1/")
    monkeypatch.setenv("DDE_MODEL", "deployment")
    monkeypatch.setenv("DDE_AUTH_MODE", "azure_identity")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    Settings(_env_file=None).require_provider()


def test_settings_fail_fast_without_provider_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "DDE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ProviderConfigurationError) as caught:
        Settings(_env_file=None).require_provider()
    assert "OPENAI_API_KEY" in str(caught.value)


def test_limit_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(DDE_MAX_PAGES=0, _env_file=None)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (InputError("x"), ExitCode.INPUT_ERROR),
        (ProviderError("x"), ExitCode.PROVIDER_ERROR),
        (SchemaOutputError("x"), ExitCode.SCHEMA_ERROR),
    ],
)
def test_stable_error_exit_mapping(error: DDEError, code: ExitCode) -> None:
    assert error.exit_code == code
