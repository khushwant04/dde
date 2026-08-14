from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from dde.cli import app

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
runner = CliRunner()


def test_doctor_is_offline_and_never_prints_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-print")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["offline_ready"] is True
    assert "do-not-print" not in result.stdout


def test_extract_fake_writes_json_stdout() -> None:
    result = runner.invoke(
        app,
        ["extract", str(SAMPLES / "documents/invoice_a.pdf"), "--provider", "fake"],
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["document"]["document_id"] == "INV-20491"
    assert output["validation"]["status"] == "pass"


def test_extract_output_file_uses_stderr_for_diagnostic(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "extract",
            str(SAMPLES / "documents/invoice_a.pdf"),
            "--provider",
            "fake",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "wrote" in result.stderr
    json.loads(output.read_text())


def test_strict_review_exit_two_preserves_json() -> None:
    result = runner.invoke(
        app,
        [
            "extract",
            str(SAMPLES / "documents/invoice_mismatch.pdf"),
            "--provider",
            "fake",
            "--strict",
        ],
    )
    assert result.exit_code == 2
    output = json.loads(result.stdout)
    assert output["document"]["total"] == "270.00"
    assert output["validation"]["issues"][0]["code"] == "TOTAL_MISMATCH"


def test_input_provider_and_schema_exit_codes(tmp_path: Path, monkeypatch) -> None:
    missing = runner.invoke(app, ["extract", str(tmp_path / "missing.txt"), "--provider", "fake"])
    assert missing.exit_code == 3
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DDE_MODEL", raising=False)
    provider = runner.invoke(app, ["extract", str(SAMPLES / "documents/invoice_c.txt")])
    assert provider.exit_code == 4
    malformed = tmp_path / "bad.json"
    malformed.write_text("{}")
    schema = runner.invoke(app, ["validate", str(malformed)])
    assert schema.exit_code == 5


def test_validate_rebuilds_tampered_metadata_and_strict_exit(tmp_path: Path) -> None:
    payload = json.loads((SAMPLES / "outputs/invoice_mismatch.json").read_text())
    payload["validation"] = {"status": "pass", "review_required": False, "issues": []}
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload))
    result = runner.invoke(app, ["validate", str(path), "--strict"])
    assert result.exit_code == 2
    output = json.loads(result.stdout)
    assert output["validation"]["status"] == "fail"


def test_batch_continues_and_writes_each_result(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ("invoice_a.pdf", "invoice_c.txt"):
        shutil.copy(SAMPLES / "documents" / name, inputs / name)
    output = tmp_path / "outputs"
    result = runner.invoke(
        app,
        ["batch", str(inputs), "--output-dir", str(output), "--provider", "fake"],
    )
    assert result.exit_code == 0
    assert sorted(path.name for path in output.glob("*.json")) == [
        "invoice_a.json",
        "invoice_c.json",
    ]
    assert result.stdout == ""
    assert '"processed": 2' in result.stderr


def test_evaluate_outputs_json_and_human_diagnostic() -> None:
    result = runner.invoke(app, ["evaluate", str(SAMPLES)])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["fixture_count"] == 11
    assert report["schema_validity"]["rate"] == 1.0
    assert report["validation_detection"] == {
        "found": 4,
        "expected": 4,
        "predicted": 4,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "true_positive": 4,
        "false_positive": 0,
        "false_negative": 0,
    }
    assert "fake-provider" in report["note"]
    assert set(report["breakdown"]) == {"format", "layout", "document_type"}
    assert set(report["breakdown"]["format"]) == {"csv", "image", "pdf", "text", "xlsx"}
    assert {
        document_type: evidence["fixtures"]
        for document_type, evidence in report["breakdown"]["document_type"].items()
    } == {"credit_note": 2, "invoice": 5, "purchase_order": 2, "receipt": 2}
    assert "evaluated 11 fixtures" in result.stderr


def test_evaluator_counts_unexpected_and_missing_issue_codes(tmp_path: Path) -> None:
    sample_copy = tmp_path / "samples"
    shutil.copytree(SAMPLES, sample_copy)
    invoice_a_path = sample_copy / "outputs/invoice_a.json"
    invoice_c_path = sample_copy / "outputs/invoice_c.json"
    invoice_a = json.loads(invoice_a_path.read_text())
    invoice_c = json.loads(invoice_c_path.read_text())
    unexpected_issue = invoice_c["validation"]["issues"][0]
    invoice_a["validation"]["issues"].append(unexpected_issue)
    invoice_a["validation"]["status"] = "warning"
    invoice_a["validation"]["review_required"] = True
    invoice_c["validation"] = {"status": "pass", "review_required": False, "issues": []}
    invoice_a_path.write_text(json.dumps(invoice_a))
    invoice_c_path.write_text(json.dumps(invoice_c))

    result = runner.invoke(app, ["evaluate", str(sample_copy)])
    assert result.exit_code == 0
    detection = json.loads(result.stdout)["validation_detection"]
    assert detection == {
        "found": 3,
        "expected": 4,
        "predicted": 4,
        "precision": 0.75,
        "recall": 0.75,
        "f1": 0.75,
        "true_positive": 3,
        "false_positive": 1,
        "false_negative": 1,
    }


def test_evaluator_reports_missing_output(tmp_path: Path) -> None:
    sample_copy = tmp_path / "samples"
    shutil.copytree(SAMPLES, sample_copy)
    (sample_copy / "outputs/invoice_c.json").unlink()
    result = runner.invoke(app, ["evaluate", str(sample_copy)])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["processing"]["count"] == 10
    assert report["validation_detection"]["expected"] == 4
    assert report["validation_detection"]["false_negative"] == 1
    assert report["validation_detection"]["recall"] == 0.75
    assert {failure["fixture"] for failure in report["failures"]} == {"invoice_c"}


def test_evaluator_counts_expected_issues_for_schema_invalid_output(tmp_path: Path) -> None:
    sample_copy = tmp_path / "samples"
    shutil.copytree(SAMPLES, sample_copy)
    (sample_copy / "outputs/invoice_mismatch.json").write_text("{}")

    result = runner.invoke(app, ["evaluate", str(sample_copy)])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["schema_validity"]["count"] == 10
    assert report["validation_detection"]["expected"] == 4
    assert report["validation_detection"]["false_negative"] == 1
    assert report["validation_detection"]["recall"] == 0.75
    assert {failure["fixture"] for failure in report["failures"]} == {"invoice_mismatch"}


def test_validate_migrates_legacy_v1_result_to_v2(tmp_path: Path) -> None:
    payload = json.loads((SAMPLES / "outputs/invoice_a.json").read_text())
    payload["schema_version"] = "1.0"
    payload["source"].pop("sheet_count")
    payload["source"].pop("notices")
    payload["document"].pop("reference_document_id")
    payload["document"].pop("delivery_date")
    path = tmp_path / "legacy-v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    migrated = json.loads(result.stdout)
    assert migrated["schema_version"] == "2.0"
    assert migrated["source"]["sheet_count"] is None
    assert migrated["source"]["notices"] == []
    expected_document = payload["document"] | {
        "reference_document_id": None,
        "delivery_date": None,
    }
    assert migrated["document"] == expected_document
