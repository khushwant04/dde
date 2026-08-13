"""Deterministic evaluator for committed fixture ground truth and result envelopes."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dde.models import ExtractedDocument, ResultEnvelope

HEADER_FIELDS = (
    "document_type",
    "document_id",
    "customer_name",
    "issue_date",
    "due_date",
    "currency",
    "subtotal",
    "discount",
    "tax",
    "shipping",
    "total",
)
DECIMAL_FIELDS = ("subtotal", "discount", "tax", "shipping", "total")


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def _line_tuple(line: Any) -> tuple[str | None, Decimal | None, Decimal | None, Decimal | None]:
    description = _normalized(line.description) if line.description is not None else None
    return (description, line.quantity, line.unit_price, line.amount)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate_samples(root: Path) -> dict[str, Any]:
    ground_dir = root / "ground_truth"
    output_dir = root / "outputs"
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    fixture_meta: dict[str, Any] = manifest.get("fixtures", {})

    ground_paths = sorted(ground_dir.glob("*.json"))
    processed = schema_valid = header_match = header_total = 0
    decimal_match = decimal_total = hallucinations = 0
    true_positive = false_positive = false_negative = 0
    issue_expected = issue_found = 0
    failures: list[dict[str, str]] = []
    format_breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"fixtures": 0, "processed": 0, "schema_valid": 0}
    )
    layout_breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"fixtures": 0, "processed": 0, "schema_valid": 0}
    )

    for ground_path in ground_paths:
        fixture_id = ground_path.stem
        metadata = fixture_meta.get(fixture_id, {})
        media_group = metadata.get("format", "unknown")
        layout_group = metadata.get("layout", "unknown")
        format_breakdown[media_group]["fixtures"] += 1
        layout_breakdown[layout_group]["fixtures"] += 1
        try:
            expected = ExtractedDocument.model_validate_json(ground_path.read_text())
        except (ValidationError, OSError) as exc:
            failures.append({"fixture": fixture_id, "error": f"invalid ground truth: {exc}"})
            continue
        output_path = output_dir / f"{fixture_id}.json"
        if not output_path.is_file():
            failures.append({"fixture": fixture_id, "error": "missing output"})
            continue
        processed += 1
        format_breakdown[media_group]["processed"] += 1
        layout_breakdown[layout_group]["processed"] += 1
        try:
            actual_result = ResultEnvelope.model_validate_json(output_path.read_text())
        except (ValidationError, OSError) as exc:
            failures.append({"fixture": fixture_id, "error": f"invalid output: {exc}"})
            continue
        schema_valid += 1
        format_breakdown[media_group]["schema_valid"] += 1
        layout_breakdown[layout_group]["schema_valid"] += 1
        actual = actual_result.document

        for field in HEADER_FIELDS:
            expected_value = getattr(expected, field)
            actual_value = getattr(actual, field)
            header_total += 1
            if _normalized(expected_value) == _normalized(actual_value):
                header_match += 1
            if expected_value is None and actual_value is not None:
                hallucinations += 1
        for field in ("name", "tax_id", "address"):
            header_total += 1
            expected_value = getattr(expected.vendor, field)
            actual_value = getattr(actual.vendor, field)
            if _normalized(expected_value) == _normalized(actual_value):
                header_match += 1
            if expected_value is None and actual_value is not None:
                hallucinations += 1
        for expected_line, actual_line in zip(expected.line_items, actual.line_items, strict=False):
            for field in ("description", "quantity", "unit_price", "amount"):
                expected_value = getattr(expected_line, field)
                actual_value = getattr(actual_line, field)
                if expected_value is None and actual_value is not None:
                    hallucinations += 1
        for field in DECIMAL_FIELDS:
            decimal_total += 1
            if getattr(expected, field) == getattr(actual, field):
                decimal_match += 1

        expected_lines = Counter(_line_tuple(line) for line in expected.line_items)
        actual_lines = Counter(_line_tuple(line) for line in actual.line_items)
        overlap = sum((expected_lines & actual_lines).values())
        true_positive += overlap
        false_positive += sum(actual_lines.values()) - overlap
        false_negative += sum(expected_lines.values()) - overlap

        expected_codes = set(fixture_meta.get(fixture_id, {}).get("expected_issue_codes", []))
        actual_codes = {issue.code.value for issue in actual_result.validation.issues}
        issue_expected += len(expected_codes)
        issue_found += len(expected_codes & actual_codes)

    precision = _rate(true_positive, true_positive + false_positive)
    recall = _rate(true_positive, true_positive + false_negative)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    return {
        "fixture_count": len(ground_paths),
        "processing": {"count": processed, "rate": _rate(processed, len(ground_paths))},
        "schema_validity": {"count": schema_valid, "rate": _rate(schema_valid, len(ground_paths))},
        "header_exact_match": {
            "matched": header_match,
            "compared": header_total,
            "rate": _rate(header_match, header_total),
        },
        "decimal_accuracy": {
            "matched": decimal_match,
            "compared": decimal_total,
            "rate": _rate(decimal_match, decimal_total),
        },
        "line_items": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "validation_detection": {
            "found": issue_found,
            "expected": issue_expected,
            "recall": _rate(issue_found, issue_expected),
        },
        "hallucination_count": hallucinations,
        "breakdown": {
            "format": dict(sorted(format_breakdown.items())),
            "layout": dict(sorted(layout_breakdown.items())),
        },
        "failures": failures,
        "note": "Committed outputs are fake-provider samples, not live model accuracy evidence.",
    }
