from __future__ import annotations

import hashlib
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image, ImageChops

_GENERATOR = runpy.run_path(Path(__file__).parents[1] / "scripts" / "generate_fixtures.py")
SAVE_PDF = cast(Callable[[Path, str, bool], None], _GENERATOR["save_pdf"])
DRAW_TWO_COLUMN = cast(Callable[[], Image.Image], _GENERATOR["draw_two_column_invoice"])
FIXTURES = cast(dict[str, dict[str, Any]], _GENERATOR["FIXTURES"])

SOURCE_DATES: dict[str, dict[str, tuple[str, str] | None]] = {
    "invoice_a": {
        "issue_date": ("12 Aug 2026", "2026-08-12"),
        "due_date": ("26 Aug 2026", "2026-08-26"),
    },
    "invoice_b": {"issue_date": ("AUG 11, 2026", "2026-08-11"), "due_date": None},
    "invoice_c": {"issue_date": ("2026/08/10", "2026-08-10"), "due_date": None},
    "invoice_d": {
        "issue_date": ("09.08.2026", "2026-08-09"),
        "due_date": ("08.08.2026", "2026-08-08"),
    },
    "receipt_a": {"issue_date": ("13/08/2026", "2026-08-13"), "due_date": None},
    "receipt_b": {"issue_date": ("2026-08-12", "2026-08-12"), "due_date": None},
    "invoice_mismatch": {
        "issue_date": ("August 13, 2026", "2026-08-13"),
        "due_date": None,
    },
}


@pytest.mark.parametrize("image_only", [False, True])
def test_generated_pdf_is_byte_reproducible(tmp_path: Path, image_only: bool) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"

    SAVE_PDF(first, "INVOICE INV-001\nWidget 2 x USD 5.00", image_only)
    SAVE_PDF(second, "INVOICE INV-001\nWidget 2 x USD 5.00", image_only)

    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).digest() == hashlib.sha256(second_bytes).digest()


@pytest.mark.parametrize("fixture_id", sorted(FIXTURES))
def test_expected_fixture_values_are_visible(fixture_id: str) -> None:
    fixture = FIXTURES[fixture_id]
    source = " ".join(str(fixture["text"]).casefold().split())
    document = cast(dict[str, Any], fixture["document"])
    vendor = cast(dict[str, Any], document["vendor"])

    visible_values = [
        document["document_type"],
        document["document_id"],
        document["customer_name"],
        document["currency"],
        vendor["name"],
        vendor["tax_id"],
        vendor["address"],
        document["subtotal"],
        document["discount"],
        document["tax"],
        document["shipping"],
        document["total"],
    ]
    for line in cast(list[dict[str, Any]], document["line_items"]):
        visible_values.extend(
            [line["description"], line["quantity"], line["unit_price"], line["amount"]]
        )

    for value in visible_values:
        if value is not None:
            assert str(value).casefold() in source, f"{fixture_id}: {value!r} is not visible"


@pytest.mark.parametrize("fixture_id", sorted(SOURCE_DATES))
def test_normalized_dates_have_explicit_source_values(fixture_id: str) -> None:
    fixture = FIXTURES[fixture_id]
    source = str(fixture["text"])
    document = cast(dict[str, Any], fixture["document"])
    for field, mapping in SOURCE_DATES[fixture_id].items():
        if mapping is None:
            assert document[field] is None
            continue
        source_value, normalized = mapping
        assert source_value in source
        assert document[field] == normalized


def test_invoice_b_renders_two_populated_columns() -> None:
    image = DRAW_TWO_COLUMN()
    assert image.width > image.height
    left = image.crop((0, 0, image.width // 2 - 20, image.height))
    right = image.crop((image.width // 2 + 20, 0, image.width, image.height))
    for column in (left, right):
        white = Image.new("RGB", column.size, "white")
        assert ImageChops.difference(column, white).getbbox() is not None


PUBLIC_DOCUMENTS = {
    "invoice_a.pdf",
    "invoice_b.png",
    "invoice_c.txt",
    "invoice_d.pdf",
    "receipt_a.jpg",
    "receipt_b.pdf",
    "invoice_mismatch.pdf",
    "bad_input.pdf",
}
PUBLIC_FIXTURE_IDS = {
    "invoice_a",
    "invoice_b",
    "invoice_c",
    "invoice_d",
    "receipt_a",
    "receipt_b",
    "invoice_mismatch",
}


def test_public_sample_tree_contains_only_generated_fixtures() -> None:
    samples = Path(__file__).parents[1] / "samples"
    expected = {"manifest.json", "evaluation-summary.json"}
    expected.update(f"documents/{name}" for name in PUBLIC_DOCUMENTS)
    for directory in ("ground_truth", "fake_responses", "outputs"):
        expected.update(f"{directory}/{fixture_id}.json" for fixture_id in PUBLIC_FIXTURE_IDS)
    actual = {path.relative_to(samples).as_posix() for path in samples.rglob("*") if path.is_file()}
    assert actual == expected
