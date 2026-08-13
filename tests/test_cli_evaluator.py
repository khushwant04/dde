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
    assert report["fixture_count"] == 7
    assert report["schema_validity"]["rate"] == 1.0
    assert report["validation_detection"]["recall"] == 1.0
    assert "fake-provider" in report["note"]
    assert set(report["breakdown"]) == {"format", "layout"}
    assert set(report["breakdown"]["format"]) == {"image", "pdf", "text"}
    assert "evaluated 7 fixtures" in result.stderr


def test_evaluator_reports_missing_output(tmp_path: Path) -> None:
    sample_copy = tmp_path / "samples"
    shutil.copytree(SAMPLES, sample_copy)
    (sample_copy / "outputs/invoice_a.json").unlink()
    result = runner.invoke(app, ["evaluate", str(sample_copy)])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["processing"]["count"] == 6
    assert {failure["fixture"] for failure in report["failures"]} == {"invoice_a"}
