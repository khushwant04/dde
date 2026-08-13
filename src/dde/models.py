"""Strict domain contracts for extraction and trusted result metadata."""

from __future__ import annotations

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

    document_type: Literal["invoice", "receipt"]
    document_id: str | None
    vendor: Vendor
    customer_name: str | None
    issue_date: str | None
    due_date: str | None
    currency: str | None
    line_items: list[LineItem]
    subtotal: NullableMoney = Field(
        description=(
            "Printed subtotal before a separately applied invoice-level discount; when the source "
            "subtotal is already net after credits, use that net subtotal and set discount null"
        )
    )
    discount: NullableMoney = Field(
        description=(
            "Separate invoice-level discount subtracted exactly once from subtotal; null when line "
            "amounts or subtotal are already net after credits or discounts"
        )
    )
    tax: NullableMoney = Field(description="Printed invoice-level tax added to subtotal")
    shipping: NullableMoney = Field(description="Printed shipping amount added to subtotal")
    total: NullableMoney = Field(description="Final printed invoice or receipt total")

    @field_serializer("subtotal", "discount", "tax", "shipping", "total", when_used="json")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class SourceMetadata(StrictModel):
    file_name: str
    media_type: str
    byte_count: int
    page_count: int
    sha256: str


class IssueCode(StrEnum):
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


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ValidationIssue(StrictModel):
    code: IssueCode
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
    schema_version: Literal["1.0"] = "1.0"
    source: SourceMetadata
    document: ExtractedDocument
    validation: ValidationMetadata
