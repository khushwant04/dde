"""Strict domain contracts for extraction and trusted result metadata."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_serializer,
)

_PLAIN_DECIMAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?\Z")


def _parse_plain_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("decimal must be finite")
        return value
    if not isinstance(value, str) or _PLAIN_DECIMAL.fullmatch(value) is None:
        raise ValueError("decimal must be a plain JSON string without exponent notation")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("decimal must be finite")
    return parsed


Money = Annotated[
    Decimal,
    BeforeValidator(_parse_plain_decimal),
    Field(
        allow_inf_nan=False,
        description=(
            "Plain decimal string without currency symbols, grouping separators, or exponent "
            "notation; examples: 10, 10.50, -0.25"
        ),
    ),
    WithJsonSchema({"type": "string"}, mode="validation"),
]
NullableMoney = Money | None
PositiveCount = Annotated[int, Field(ge=1)]
DocumentType = Literal["invoice", "receipt", "purchase_order", "credit_note"]


class StrictModel(BaseModel):
    """Base model used at every trust boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Vendor(StrictModel):
    name: str | None
    tax_id: str | None
    address: str | None


class LineItem(StrictModel):
    description: str | None = Field(
        description="Visible line description, including service period or code when useful"
    )
    quantity: NullableMoney = Field(
        description="Printed quantity as a plain decimal string, or null when not shown"
    )
    unit_price: NullableMoney = Field(
        description="Printed per-unit or charge amount; preserve a visible negative sign"
    )
    amount: NullableMoney = Field(
        description=(
            "Printed final line amount contributing to subtotal; preserve negative credits or "
            "reversals and use an explicitly printed net line amount when present"
        )
    )

    @field_serializer("quantity", "unit_price", "amount", when_used="json")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class ExtractedDocument(StrictModel):
    """Only this model is returned by the model provider."""

    document_type: DocumentType
    document_id: str | None
    reference_document_id: str | None = Field(
        description=(
            "Visible identifier of the invoice or other document referenced by a credit note; "
            "null when absent or not a credit note"
        )
    )
    vendor: Vendor
    customer_name: str | None
    issue_date: str | None
    due_date: str | None
    delivery_date: str | None = Field(
        description=(
            "Visible requested or promised delivery date for a purchase order; null when absent "
            "or not a purchase order"
        )
    )
    currency: str | None
    line_items: list[LineItem]
    subtotal: NullableMoney = Field(
        description=(
            "Printed subtotal before a separately applied document-level discount; when the "
            "source subtotal is already net after credits, use that net subtotal and set "
            "discount null"
        )
    )
    discount: NullableMoney = Field(
        description=(
            "Separate document-level discount subtracted exactly once from subtotal; null when "
            "line amounts or subtotal are already net after credits or discounts"
        )
    )
    tax: NullableMoney = Field(description="Printed document-level tax added to subtotal")
    shipping: NullableMoney = Field(description="Printed shipping amount added to subtotal")
    total: NullableMoney = Field(description="Final printed document total")

    @field_serializer("subtotal", "discount", "tax", "shipping", "total", when_used="json")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class IssueCode(StrEnum):
    LINE_AMOUNT_MISMATCH = "LINE_AMOUNT_MISMATCH"
    SUBTOTAL_MISMATCH = "SUBTOTAL_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    INVALID_DATE = "INVALID_DATE"
    DUE_BEFORE_ISSUE = "DUE_BEFORE_ISSUE"
    DELIVERY_BEFORE_ISSUE = "DELIVERY_BEFORE_ISSUE"
    UNKNOWN_CURRENCY = "UNKNOWN_CURRENCY"
    MISSING_IDENTIFIER = "MISSING_IDENTIFIER"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    NO_LINE_ITEMS = "NO_LINE_ITEMS"
    NEGATIVE_VALUE = "NEGATIVE_VALUE"
    BALANCED_REVERSAL = "BALANCED_REVERSAL"
    DUPLICATE_LINE = "DUPLICATE_LINE"
    CREDIT_SIGN_INCONSISTENCY = "CREDIT_SIGN_INCONSISTENCY"
    CREDIT_TOTAL_UNVERIFIABLE = "CREDIT_TOTAL_UNVERIFIABLE"


class LoaderNoticeCode(StrEnum):
    NO_NATIVE_TEXT = "NO_NATIVE_TEXT"
    CSV_DIALECT_FALLBACK = "CSV_DIALECT_FALLBACK"
    XLSX_HIDDEN_SHEET_SKIPPED = "XLSX_HIDDEN_SHEET_SKIPPED"
    XLSX_FORMULA_PRESENT = "XLSX_FORMULA_PRESENT"
    XLSX_FORMULA_CACHE_MISSING = "XLSX_FORMULA_CACHE_MISSING"


class LoaderNotice(StrictModel):
    """Trusted, non-sensitive evidence emitted by guarded loaders."""

    code: LoaderNoticeCode
    severity: Severity
    message: str
    field: str | None


class SourceMetadata(StrictModel):
    file_name: str
    media_type: str
    byte_count: int
    page_count: PositiveCount | None
    sheet_count: PositiveCount | None
    sha256: str
    notices: list[LoaderNotice]


ValidationCode = IssueCode | LoaderNoticeCode


class ValidationStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ValidationIssue(StrictModel):
    code: ValidationCode
    severity: Severity
    message: str
    field: str | None
    expected: str | None
    actual: str | None


class ValidationMetadata(StrictModel):
    status: ValidationStatus
    review_required: bool
    issues: list[ValidationIssue]


class ResultEnvelope(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    source: SourceMetadata
    document: ExtractedDocument
    validation: ValidationMetadata


class _LegacyExtractedDocumentV1(StrictModel):
    """Exact schema-v1 provider document; intentionally excludes all v2 domain additions."""

    document_type: Literal["invoice", "receipt"]
    document_id: str | None
    vendor: Vendor
    customer_name: str | None
    issue_date: str | None
    due_date: str | None
    currency: str | None
    line_items: list[LineItem]
    subtotal: NullableMoney
    discount: NullableMoney
    tax: NullableMoney
    shipping: NullableMoney
    total: NullableMoney


class _LegacyIssueCodeV1(StrEnum):
    LINE_AMOUNT_MISMATCH = "LINE_AMOUNT_MISMATCH"
    SUBTOTAL_MISMATCH = "SUBTOTAL_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    INVALID_DATE = "INVALID_DATE"
    DUE_BEFORE_ISSUE = "DUE_BEFORE_ISSUE"
    UNKNOWN_CURRENCY = "UNKNOWN_CURRENCY"
    MISSING_IDENTIFIER = "MISSING_IDENTIFIER"
    NO_LINE_ITEMS = "NO_LINE_ITEMS"
    NEGATIVE_VALUE = "NEGATIVE_VALUE"
    BALANCED_REVERSAL = "BALANCED_REVERSAL"
    DUPLICATE_LINE = "DUPLICATE_LINE"


class _LegacySourceMetadataV1(StrictModel):
    file_name: str
    media_type: str
    byte_count: int
    page_count: int
    sha256: str


class _LegacyValidationIssueV1(StrictModel):
    code: _LegacyIssueCodeV1
    severity: Severity
    message: str
    field: str | None
    expected: str | None
    actual: str | None


class _LegacyValidationMetadataV1(StrictModel):
    status: ValidationStatus
    review_required: bool
    issues: list[_LegacyValidationIssueV1]


class _LegacyResultEnvelopeV1(StrictModel):
    schema_version: Literal["1.0"]
    source: _LegacySourceMetadataV1
    document: _LegacyExtractedDocumentV1
    validation: _LegacyValidationMetadataV1


def parse_result_envelope_json(value: str) -> ResultEnvelope:
    """Parse v2 or explicitly migrate a valid v1 envelope for offline revalidation."""
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Result JSON must be an object")
    version = payload.get("schema_version")
    if version == "2.0":
        return ResultEnvelope.model_validate_json(value)
    if version == "1.0":
        legacy = _LegacyResultEnvelopeV1.model_validate_json(value)
        if legacy.source.page_count < 1:
            raise ValueError("Schema v1 page_count must be positive to migrate to schema v2")
        document_data = legacy.document.model_dump()
        document_data["reference_document_id"] = None
        document_data["delivery_date"] = None
        return ResultEnvelope(
            source=SourceMetadata(
                file_name=legacy.source.file_name,
                media_type=legacy.source.media_type,
                byte_count=legacy.source.byte_count,
                page_count=legacy.source.page_count,
                sheet_count=None,
                sha256=legacy.source.sha256,
                notices=[],
            ),
            document=ExtractedDocument.model_validate(document_data),
            validation=ValidationMetadata(
                status=legacy.validation.status,
                review_required=legacy.validation.review_required,
                issues=[
                    ValidationIssue(
                        code=IssueCode(issue.code.value),
                        severity=issue.severity,
                        message=issue.message,
                        field=issue.field,
                        expected=issue.expected,
                        actual=issue.actual,
                    )
                    for issue in legacy.validation.issues
                ],
            ),
        )
    raise ValueError(f"Unsupported result schema_version: {version!r}")
