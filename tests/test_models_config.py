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
from dde.models import (
    ExtractedDocument,
    ResultEnvelope,
    parse_result_envelope_json,
)


def document_json() -> dict[str, object]:
    return {
        "document_type": "invoice",
        "document_id": None,
        "reference_document_id": None,
        "vendor": {"name": "Vendor", "tax_id": None, "address": None},
        "customer_name": None,
        "issue_date": None,
        "due_date": None,
        "delivery_date": None,
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


@pytest.mark.parametrize("document_type", ["invoice", "receipt", "purchase_order", "credit_note"])
def test_all_supported_document_types_parse(document_type: str) -> None:
    payload = document_json()
    payload["document_type"] = document_type
    assert ExtractedDocument.model_validate_json(json.dumps(payload)).document_type == document_type


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
    del payload["delivery_date"]
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


@pytest.mark.parametrize(
    "alias",
    [
        "DDE_MAX_PAGES",
        "DDE_MAX_TABULAR_ROWS",
        "DDE_MAX_TABULAR_COLUMNS",
        "DDE_MAX_CELL_CHARS",
        "DDE_MAX_TABULAR_CHARS",
        "DDE_MAX_SHEETS",
        "DDE_MAX_XLSX_ZIP_ENTRIES",
        "DDE_MAX_XLSX_UNCOMPRESSED_BYTES",
        "DDE_MAX_REQUEST_BYTES",
        "DDE_MAX_CONCURRENT_REQUESTS",
        "DDE_API_TIMEOUT_SECONDS",
    ],
)
def test_limit_validation(alias: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({alias: 0})


def test_tabular_limits_are_visible_in_safe_summary() -> None:
    summary = Settings(_env_file=None).safe_summary()
    assert summary["max_tabular_rows"] == 10_000
    assert summary["max_tabular_columns"] == 100
    assert summary["max_cell_chars"] == 4_096
    assert summary["max_tabular_chars"] == 200_000
    assert summary["max_sheets"] == 20
    assert summary["max_xlsx_zip_entries"] == 1_000
    assert summary["max_xlsx_uncompressed_bytes"] == 52_428_800
    assert summary["max_request_bytes"] == 16_777_216
    assert summary["max_concurrent_requests"] == 2
    assert summary["api_timeout_seconds"] == 130.0


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


def legacy_document_json() -> dict[str, object]:
    payload = document_json()
    del payload["reference_document_id"]
    del payload["delivery_date"]
    return payload


def legacy_v1_result_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "source": {
                "file_name": "legacy.pdf",
                "media_type": "application/pdf",
                "byte_count": 100,
                "page_count": 1,
                "sha256": "a" * 64,
            },
            "document": legacy_document_json(),
            "validation": {"status": "pass", "review_required": False, "issues": []},
        }
    )


def test_v1_result_is_explicitly_migrated_to_v2_for_revalidation() -> None:
    migrated = parse_result_envelope_json(legacy_v1_result_json())
    assert migrated.schema_version == "2.0"
    assert migrated.source.page_count == 1
    assert migrated.source.sheet_count is None
    assert migrated.source.notices == []
    assert migrated.document.reference_document_id is None
    assert migrated.document.delivery_date is None
    ResultEnvelope.model_validate_json(migrated.model_dump_json())


@pytest.mark.parametrize("page_count", [0, -1])
def test_v1_migration_rejects_page_counts_not_representable_in_v2(page_count: int) -> None:
    payload = json.loads(legacy_v1_result_json())
    payload["source"]["page_count"] = page_count
    with pytest.raises(ValueError, match="must be positive to migrate"):
        parse_result_envelope_json(json.dumps(payload))


def test_direct_v2_parser_rejects_v1_and_unknown_versions() -> None:
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate_json(legacy_v1_result_json())
    payload = json.loads(legacy_v1_result_json())
    payload["schema_version"] = "9.0"
    with pytest.raises(ValueError, match="Unsupported result schema_version"):
        parse_result_envelope_json(json.dumps(payload))


def test_v2_source_page_and_sheet_counts_are_positive_when_present() -> None:
    payload = json.loads(parse_result_envelope_json(legacy_v1_result_json()).model_dump_json())
    payload["source"]["sheet_count"] = 0
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate(payload)


@pytest.mark.parametrize("v2_only_code", ["NO_NATIVE_TEXT", "MISSING_REFERENCE"])
def test_v1_migration_rejects_v2_only_issue_codes(v2_only_code: str) -> None:
    payload = json.loads(legacy_v1_result_json())
    payload["validation"]["issues"] = [
        {
            "code": v2_only_code,
            "severity": "warning",
            "message": "v2-only issue",
            "field": None,
            "expected": None,
            "actual": None,
        }
    ]
    with pytest.raises(ValidationError):
        parse_result_envelope_json(json.dumps(payload))


def test_v1_migration_rejects_v2_document_fields_and_types() -> None:
    payload = json.loads(legacy_v1_result_json())
    payload["document"]["reference_document_id"] = None
    with pytest.raises(ValidationError):
        parse_result_envelope_json(json.dumps(payload))
    payload = json.loads(legacy_v1_result_json())
    payload["document"]["document_type"] = "credit_note"
    with pytest.raises(ValidationError):
        parse_result_envelope_json(json.dumps(payload))
