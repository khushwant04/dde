"""Deterministic validation rules over immutable extracted values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from dde.models import (
    ExtractedDocument,
    IssueCode,
    LineItem,
    Severity,
    ValidationIssue,
    ValidationMetadata,
    ValidationStatus,
)

TOLERANCE = Decimal("0.01")
KNOWN_CURRENCIES = frozenset(
    {
        "AED",
        "AUD",
        "BDT",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "IDR",
        "ILS",
        "INR",
        "JPY",
        "KRW",
        "MXN",
        "MYR",
        "NOK",
        "NZD",
        "PHP",
        "PLN",
        "RUB",
        "SAR",
        "SEK",
        "SGD",
        "THB",
        "TRY",
        "TWD",
        "USD",
        "VND",
        "ZAR",
    }
)


def _issue(
    code: IssueCode,
    severity: Severity,
    message: str,
    field: str | None = None,
    expected: Decimal | str | None = None,
    actual: Decimal | str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        field=field,
        expected=None if expected is None else str(expected),
        actual=None if actual is None else str(actual),
    )


def _different(left: Decimal, right: Decimal, tolerance: Decimal) -> bool:
    return abs(left - right) > tolerance


ReversalKey = tuple[str, Decimal | None, Decimal | None, Decimal]


def _reversal_key(line: LineItem) -> ReversalKey | None:
    if line.description is None or line.amount is None or line.amount == 0:
        return None
    description = " ".join(line.description.casefold().split())
    return (
        description,
        None if line.quantity is None else abs(line.quantity),
        None if line.unit_price is None else abs(line.unit_price),
        abs(line.amount),
    )


def _balanced_reversal_pairs(lines: list[LineItem]) -> list[tuple[int, int]]:
    positive_by_key: dict[ReversalKey, list[int]] = {}
    for index, line in enumerate(lines):
        key = _reversal_key(line)
        if key is not None and line.amount is not None and line.amount > 0:
            positive_by_key.setdefault(key, []).append(index)

    pairs: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        key = _reversal_key(line)
        if key is None or line.amount is None or line.amount >= 0:
            continue
        candidates = positive_by_key.get(key)
        if candidates:
            pairs.append((candidates.pop(0), index))
    return pairs


def _parse_date(value: str, field: str, issues: list[ValidationIssue]) -> date | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        issues.append(
            _issue(
                IssueCode.INVALID_DATE,
                Severity.ERROR,
                "Date must be a real calendar date in YYYY-MM-DD format",
                field,
                "YYYY-MM-DD",
                value,
            )
        )
        return None
    return parsed


def validate_document(
    document: ExtractedDocument, tolerance: Decimal = TOLERANCE
) -> ValidationMetadata:
    """Return trusted issues. The supplied document is never modified."""
    issues: list[ValidationIssue] = []

    issue_date = (
        _parse_date(document.issue_date, "issue_date", issues) if document.issue_date else None
    )
    due_date = _parse_date(document.due_date, "due_date", issues) if document.due_date else None
    if issue_date is not None and due_date is not None and due_date < issue_date:
        issues.append(
            _issue(
                IssueCode.DUE_BEFORE_ISSUE,
                Severity.WARNING,
                "Due date precedes issue date",
                "due_date",
                issue_date.isoformat(),
                due_date.isoformat(),
            )
        )

    if document.currency is None or document.currency not in KNOWN_CURRENCIES:
        issues.append(
            _issue(
                IssueCode.UNKNOWN_CURRENCY,
                Severity.WARNING,
                "Currency is absent or is not a recognized ISO 4217 code",
                "currency",
                "ISO 4217 code",
                document.currency,
            )
        )
    if not document.document_id:
        issues.append(
            _issue(
                IssueCode.MISSING_IDENTIFIER,
                Severity.WARNING,
                "Document identifier is absent",
                "document_id",
            )
        )
    if not document.line_items:
        issues.append(
            _issue(
                IssueCode.NO_LINE_ITEMS,
                Severity.WARNING,
                "No line items were extracted",
                "line_items",
            )
        )

    reversal_pairs = _balanced_reversal_pairs(document.line_items)
    balanced_negative_indices = {negative for _, negative in reversal_pairs}
    for positive, negative in reversal_pairs:
        issues.append(
            _issue(
                IssueCode.BALANCED_REVERSAL,
                Severity.INFO,
                "Negative line exactly reverses a positive line",
                f"line_items.{negative}",
                f"line_items.{positive}",
                f"line_items.{negative}",
            )
        )

    negative_fields: list[tuple[str, Decimal | None]] = [
        ("subtotal", document.subtotal),
        ("discount", document.discount),
        ("tax", document.tax),
        ("shipping", document.shipping),
        ("total", document.total),
    ]
    for index, line in enumerate(document.line_items):
        if index not in balanced_negative_indices:
            negative_fields.extend(
                [
                    (f"line_items.{index}.quantity", line.quantity),
                    (f"line_items.{index}.unit_price", line.unit_price),
                    (f"line_items.{index}.amount", line.amount),
                ]
            )
        if line.quantity is not None and line.unit_price is not None and line.amount is not None:
            expected = line.quantity * line.unit_price
            if _different(expected, line.amount, tolerance):
                issues.append(
                    _issue(
                        IssueCode.LINE_AMOUNT_MISMATCH,
                        Severity.WARNING,
                        "Quantity multiplied by unit price differs from line amount",
                        f"line_items.{index}.amount",
                        expected,
                        line.amount,
                    )
                )
        if index and line == document.line_items[index - 1]:
            issues.append(
                _issue(
                    IssueCode.DUPLICATE_LINE,
                    Severity.WARNING,
                    "Adjacent line item exactly duplicates the previous line",
                    f"line_items.{index}",
                )
            )

    for field, value in negative_fields:
        if value is not None and value < 0:
            issues.append(
                _issue(
                    IssueCode.NEGATIVE_VALUE,
                    Severity.ERROR,
                    "Negative values are unsupported",
                    field,
                    "non-negative",
                    value,
                )
            )

    amounts = [line.amount for line in document.line_items]
    if document.subtotal is not None and amounts and all(value is not None for value in amounts):
        amount_sum = sum((value for value in amounts if value is not None), Decimal(0))
        if _different(amount_sum, document.subtotal, tolerance):
            issues.append(
                _issue(
                    IssueCode.SUBTOTAL_MISMATCH,
                    Severity.ERROR,
                    "Sum of line amounts differs from subtotal",
                    "subtotal",
                    amount_sum,
                    document.subtotal,
                )
            )

    if document.subtotal is not None and document.total is not None:
        expected_total = (
            document.subtotal
            - (document.discount or Decimal(0))
            + (document.tax or Decimal(0))
            + (document.shipping or Decimal(0))
        )
        if _different(expected_total, document.total, tolerance):
            issues.append(
                _issue(
                    IssueCode.TOTAL_MISMATCH,
                    Severity.ERROR,
                    "Subtotal minus discount plus tax and shipping differs from total",
                    "total",
                    expected_total,
                    document.total,
                )
            )

    has_error = any(issue.severity == Severity.ERROR for issue in issues)
    has_warning = any(issue.severity == Severity.WARNING for issue in issues)
    status = (
        ValidationStatus.FAIL
        if has_error
        else ValidationStatus.WARNING
        if has_warning
        else ValidationStatus.PASS
    )
    return ValidationMetadata(
        status=status,
        review_required=has_error or has_warning,
        issues=issues,
    )
