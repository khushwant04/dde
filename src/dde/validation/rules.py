"""Deterministic validation rules over immutable extracted values."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from dde.models import (
    ExtractedDocument,
    IssueCode,
    LineItem,
    LoaderNotice,
    Severity,
    ValidationCode,
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
    code: ValidationCode,
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


def _credit_sign_profile(
    document: ExtractedDocument, reversal_pairs: Sequence[tuple[int, int]]
) -> tuple[str | None, list[str]]:
    """Return a supported credit polarity and fields that contradict it.

    Zero values do not establish polarity. Exact balanced reversal rows are neutral and excluded.
    Non-zero line amounts, subtotal, and total establish either a positive-magnitude or a
    negative-signed profile. Discount, tax, and shipping must use that same polarity because the
    total equation remains ``subtotal - discount + tax + shipping`` for both profiles.
    """
    neutral_line_indices = {index for pair in reversal_pairs for index in pair}
    core_values = [
        (f"line_items.{index}.amount", line.amount)
        for index, line in enumerate(document.line_items)
        if index not in neutral_line_indices
    ]
    core_values.extend((field, getattr(document, field)) for field in ("subtotal", "total"))
    non_zero_core = [(field, value) for field, value in core_values if value not in (None, 0)]
    signs = {value > 0 for _, value in non_zero_core if value is not None}
    if len(signs) > 1:
        return None, [field for field, _ in non_zero_core]
    if not signs:
        return None, []

    positive_profile = signs.pop()
    contradictions: list[str] = []
    for field in ("discount", "tax", "shipping"):
        value = getattr(document, field)
        if value not in (None, 0) and (value > 0) != positive_profile:
            contradictions.append(field)
    return ("positive-magnitude" if positive_profile else "negative-signed"), contradictions


def validate_document(
    document: ExtractedDocument,
    tolerance: Decimal = TOLERANCE,
    loader_notices: Sequence[LoaderNotice] = (),
) -> ValidationMetadata:
    """Return trusted issues. The supplied document is never modified."""
    issues: list[ValidationIssue] = []

    issue_date = (
        _parse_date(document.issue_date, "issue_date", issues) if document.issue_date else None
    )
    due_date = _parse_date(document.due_date, "due_date", issues) if document.due_date else None
    delivery_date = (
        _parse_date(document.delivery_date, "delivery_date", issues)
        if document.delivery_date
        else None
    )
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
    if issue_date is not None and delivery_date is not None and delivery_date < issue_date:
        issues.append(
            _issue(
                IssueCode.DELIVERY_BEFORE_ISSUE,
                Severity.WARNING,
                "Delivery date precedes issue date",
                "delivery_date",
                issue_date.isoformat(),
                delivery_date.isoformat(),
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
    if document.document_type == "credit_note" and not document.reference_document_id:
        issues.append(
            _issue(
                IssueCode.MISSING_REFERENCE,
                Severity.WARNING,
                "Credit note does not identify the referenced document",
                "reference_document_id",
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

    is_credit_note = document.document_type == "credit_note"
    if not is_credit_note:
        for field, value in negative_fields:
            if value is not None and value < 0:
                issues.append(
                    _issue(
                        IssueCode.NEGATIVE_VALUE,
                        Severity.ERROR,
                        "Negative values are unsupported for this document type",
                        field,
                        "non-negative",
                        value,
                    )
                )

    credit_profile: str | None = None
    credit_sign_consistent = True
    if is_credit_note:
        credit_profile, contradictory_fields = _credit_sign_profile(document, reversal_pairs)
        if contradictory_fields:
            credit_sign_consistent = False
            issues.append(
                _issue(
                    IssueCode.CREDIT_SIGN_INCONSISTENCY,
                    Severity.ERROR,
                    "Credit-note monetary values do not form one supported sign profile",
                    "document",
                    "all non-zero values positive-magnitude or all negative-signed",
                    ", ".join(contradictory_fields),
                )
            )
        elif credit_profile is None:
            issues.append(
                _issue(
                    IssueCode.CREDIT_TOTAL_UNVERIFIABLE,
                    Severity.WARNING,
                    "Credit-note polarity cannot be established from non-zero monetary values",
                    "document",
                )
            )

        incomplete_fields = [
            field for field in ("subtotal", "total") if getattr(document, field) is None
        ]
        if document.line_items and any(line.amount is None for line in document.line_items):
            incomplete_fields.append("line_items.amount")
        if incomplete_fields and credit_sign_consistent and credit_profile is not None:
            issues.append(
                _issue(
                    IssueCode.CREDIT_TOTAL_UNVERIFIABLE,
                    Severity.WARNING,
                    "Credit-note arithmetic cannot be fully verified because values are absent",
                    "document",
                    "line amounts, subtotal, and total",
                    ", ".join(incomplete_fields),
                )
            )

    amounts = [line.amount for line in document.line_items]
    can_check_credit_arithmetic = not is_credit_note or (
        credit_sign_consistent and credit_profile is not None
    )
    if (
        can_check_credit_arithmetic
        and document.subtotal is not None
        and amounts
        and all(value is not None for value in amounts)
    ):
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

    if can_check_credit_arithmetic and document.subtotal is not None and document.total is not None:
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

    issues.extend(
        ValidationIssue(
            code=notice.code,
            severity=notice.severity,
            message=notice.message,
            field=notice.field,
            expected=None,
            actual=None,
        )
        for notice in loader_notices
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
