from __future__ import annotations

from decimal import Decimal

import pytest

from dde.models import (
    ExtractedDocument,
    IssueCode,
    LineItem,
    Severity,
    ValidationStatus,
    Vendor,
)
from dde.validation import validate_document

D = Decimal


def make_document(**updates: object) -> ExtractedDocument:
    values: dict[str, object] = {
        "document_type": "invoice",
        "document_id": "INV-1",
        "vendor": Vendor(name="Vendor", tax_id=None, address=None),
        "customer_name": None,
        "issue_date": "2024-02-29",
        "due_date": "2024-03-30",
        "currency": "USD",
        "line_items": [
            LineItem(description="Item", quantity=D("2"), unit_price=D("5"), amount=D("10"))
        ],
        "subtotal": D("10"),
        "discount": None,
        "tax": D("1"),
        "shipping": None,
        "total": D("11"),
    }
    values.update(updates)
    return ExtractedDocument.model_validate(values)


def codes(document: ExtractedDocument) -> list[IssueCode]:
    return [issue.code for issue in validate_document(document).issues]


def test_clean_document_passes() -> None:
    result = validate_document(make_document())
    assert result.status == ValidationStatus.PASS
    assert result.review_required is False
    assert result.issues == []


def test_line_amount_mismatch_and_tolerance_boundary() -> None:
    line = LineItem(description="Item", quantity=D("2"), unit_price=D("5"), amount=D("10.01"))
    assert IssueCode.LINE_AMOUNT_MISMATCH not in codes(make_document(line_items=[line]))
    line = line.model_copy(update={"amount": D("10.02")})
    assert IssueCode.LINE_AMOUNT_MISMATCH in codes(make_document(line_items=[line]))


def test_subtotal_mismatch() -> None:
    assert IssueCode.SUBTOTAL_MISMATCH in codes(make_document(subtotal=D("12"), total=D("13")))


def test_total_formula_mismatch_preserves_value() -> None:
    document = make_document(total=D("99"))
    before = document.model_copy(deep=True)
    result = validate_document(document)
    issue = next(issue for issue in result.issues if issue.code == IssueCode.TOTAL_MISMATCH)
    assert issue.expected == "11"
    assert issue.actual == "99"
    assert document == before


@pytest.mark.parametrize("value", ["2023-02-29", "08/13/2026", "2026-8-03", "not-a-date"])
def test_invalid_dates(value: str) -> None:
    assert IssueCode.INVALID_DATE in codes(make_document(issue_date=value))


def test_valid_leap_day() -> None:
    assert IssueCode.INVALID_DATE not in codes(make_document(issue_date="2024-02-29"))


def test_due_before_issue() -> None:
    assert IssueCode.DUE_BEFORE_ISSUE in codes(
        make_document(issue_date="2026-08-13", due_date="2026-08-12")
    )


@pytest.mark.parametrize("currency", [None, "XYZ", "usd"])
def test_unknown_currency(currency: str | None) -> None:
    assert IssueCode.UNKNOWN_CURRENCY in codes(make_document(currency=currency))


def test_missing_identifier_and_no_lines() -> None:
    found = codes(make_document(document_id=None, line_items=[], subtotal=None, total=None))
    assert IssueCode.MISSING_IDENTIFIER in found
    assert IssueCode.NO_LINE_ITEMS in found


@pytest.mark.parametrize(
    ("field", "value"),
    [("subtotal", D("-1")), ("discount", D("-1")), ("tax", D("-1")), ("total", D("-1"))],
)
def test_negative_header_values(field: str, value: Decimal) -> None:
    assert IssueCode.NEGATIVE_VALUE in codes(make_document(**{field: value}))


def test_negative_line_value() -> None:
    line = LineItem(description="Credit", quantity=D("-1"), unit_price=D("5"), amount=D("-5"))
    assert IssueCode.NEGATIVE_VALUE in codes(make_document(line_items=[line]))


def test_balanced_reversal_is_informational_and_does_not_require_review() -> None:
    positive = LineItem(
        description="Cloud service", quantity=None, unit_price=D("25"), amount=D("29.50")
    )
    reversal = LineItem(
        description="  cloud   SERVICE ",
        quantity=None,
        unit_price=D("-25"),
        amount=D("-29.50"),
    )
    result = validate_document(
        make_document(
            line_items=[positive, reversal],
            subtotal=D("0"),
            tax=D("0"),
            total=D("0"),
        )
    )
    assert [issue.code for issue in result.issues] == [IssueCode.BALANCED_REVERSAL]
    assert result.issues[0].severity == Severity.INFO
    assert result.status == ValidationStatus.PASS
    assert result.review_required is False


def test_only_one_duplicate_reversal_can_match_each_positive_line() -> None:
    positive = LineItem(description="Service", quantity=None, unit_price=D("5"), amount=D("5"))
    reversal = LineItem(description="Service", quantity=None, unit_price=D("-5"), amount=D("-5"))
    found = codes(
        make_document(
            line_items=[positive, reversal, reversal],
            subtotal=D("-5"),
            tax=D("0"),
            total=D("-5"),
        )
    )
    assert found.count(IssueCode.BALANCED_REVERSAL) == 1
    assert IssueCode.NEGATIVE_VALUE in found


def test_adjacent_duplicate_only() -> None:
    line = make_document().line_items[0]
    assert IssueCode.DUPLICATE_LINE in codes(make_document(line_items=[line, line]))
    other = line.model_copy(update={"description": "Other"})
    assert IssueCode.DUPLICATE_LINE not in codes(make_document(line_items=[line, other]))


def test_warning_status_and_review_are_deterministic() -> None:
    result = validate_document(make_document(document_id=None))
    assert result.status == ValidationStatus.WARNING
    assert result.review_required is True


def test_error_status_requires_review() -> None:
    result = validate_document(make_document(total=D("99")))
    assert result.status == ValidationStatus.FAIL
    assert result.review_required is True


def test_incomplete_decimal_inputs_do_not_invent_checks() -> None:
    line = LineItem(description="Unknown", quantity=None, unit_price=D("5"), amount=None)
    found = codes(make_document(line_items=[line], subtotal=None, total=None))
    assert IssueCode.LINE_AMOUNT_MISMATCH not in found
    assert IssueCode.SUBTOTAL_MISMATCH not in found
    assert IssueCode.TOTAL_MISMATCH not in found
