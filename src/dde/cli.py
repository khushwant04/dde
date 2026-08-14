"""Non-interactive CLI transport for the DDE core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from dde.config import Settings
from dde.errors import DDEError, ExitCode, InputError, SchemaOutputError
from dde.evaluator import evaluate_samples
from dde.formats import is_supported_path
from dde.models import parse_result_envelope_json
from dde.pipeline import ExtractionPipeline
from dde.providers import FakeProvider, OpenAIResponsesProvider
from dde.providers.base import ExtractionProvider
from dde.validation import validate_document

app = typer.Typer(
    name="dde",
    help=(
        "Extract and deterministically validate invoices, receipts, purchase orders, and "
        "credit notes."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _emit_json(value: str, output: Path | None) -> None:
    if output is None:
        typer.echo(value)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(value + "\n", encoding="utf-8")
    typer.echo(f"wrote {output}", err=True)


def _fail(error: Exception, code: int) -> NoReturn:
    typer.echo(f"error: {error}", err=True)
    raise typer.Exit(code)


def _settings(model: str | None = None) -> Settings:
    try:
        settings = Settings()
    except ValidationError:
        _fail(ValueError("invalid environment configuration"), ExitCode.PROVIDER_ERROR)
    if model is not None:
        settings.model = model
    return settings


def _pipeline(provider_name: str, model: str | None, fake_response_dir: Path) -> ExtractionPipeline:
    settings = _settings(model)
    provider: ExtractionProvider
    if provider_name == "fake":
        provider = FakeProvider(fixture_dir=fake_response_dir)
    elif provider_name == "openai":
        provider = OpenAIResponsesProvider(settings)
    else:
        _fail(ValueError("provider must be 'openai' or 'fake'"), ExitCode.PROVIDER_ERROR)
    return ExtractionPipeline(settings, provider)


def _run_extract(
    input_path: Path,
    output: Path | None,
    provider_name: str,
    model: str | None,
    fake_response_dir: Path,
    strict: bool,
) -> None:
    try:
        result = _pipeline(provider_name, model, fake_response_dir).run(input_path)
        _emit_json(result.model_dump_json(indent=2), output)
        if strict and result.validation.review_required:
            raise typer.Exit(ExitCode.REVIEW_REQUIRED)
    except DDEError as exc:
        _fail(exc, exc.exit_code)


@app.command()
def doctor() -> None:
    """Report local readiness without making a provider request or exposing secrets."""
    settings = _settings()
    summary = settings.safe_summary()
    summary["offline_ready"] = True
    summary["provider_ready"] = all(
        [
            summary["base_url_configured"],
            summary["model"],
            summary["credential_configured"],
        ]
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@app.command()
def extract(
    input_path: Annotated[Path, typer.Argument(exists=False, dir_okay=False, metavar="INPUT")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    provider: Annotated[str, typer.Option("--provider")] = "openai",
    fake_response_dir: Annotated[Path, typer.Option("--fake-response-dir")] = Path(
        "samples/fake_responses"
    ),
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Extract one supported document into a versioned JSON envelope."""
    _run_extract(input_path, output, provider, model, fake_response_dir, strict)


@app.command()
def batch(
    directory: Annotated[Path, typer.Argument(exists=False, file_okay=False)],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
    model: Annotated[str | None, typer.Option("--model")] = None,
    provider: Annotated[str, typer.Option("--provider")] = "openai",
    fake_response_dir: Annotated[Path, typer.Option("--fake-response-dir")] = Path(
        "samples/fake_responses"
    ),
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Extract all supported files in one directory; continue after per-file failures."""
    if not directory.is_dir():
        _fail(InputError(f"Directory does not exist: {directory}"), ExitCode.INPUT_ERROR)
    try:
        pipeline = _pipeline(provider, model, fake_response_dir)
    except DDEError as exc:
        _fail(exc, exc.exit_code)
    paths = sorted(
        path for path in directory.iterdir() if path.is_file() and is_supported_path(path)
    )
    if not paths:
        _fail(InputError("Directory contains no supported files"), ExitCode.INPUT_ERROR)
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[DDEError] = []
    review_required = False
    for path in paths:
        try:
            result = pipeline.run(path)
            (output_dir / f"{path.stem}.json").write_text(
                result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            review_required |= result.validation.review_required
            typer.echo(f"processed {path.name}", err=True)
        except DDEError as exc:
            failures.append(exc)
            typer.echo(f"failed {path.name}: {exc}", err=True)
    typer.echo(
        json.dumps({"processed": len(paths) - len(failures), "failed": len(failures)}),
        err=True,
    )
    if failures:
        raise typer.Exit(max(int(error.exit_code) for error in failures))
    if strict and review_required:
        raise typer.Exit(ExitCode.REVIEW_REQUIRED)


@app.command(name="validate")
def validate_result(
    result_json: Annotated[Path, typer.Argument(exists=False, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Revalidate a saved envelope without provider access."""
    try:
        if not result_json.is_file():
            raise InputError(f"Result file does not exist: {result_json}")
        result = parse_result_envelope_json(result_json.read_text(encoding="utf-8"))
        result = result.model_copy(
            update={
                "validation": validate_document(
                    result.document, loader_notices=result.source.notices
                )
            }
        )
        _emit_json(result.model_dump_json(indent=2), output)
        if strict and result.validation.review_required:
            raise typer.Exit(ExitCode.REVIEW_REQUIRED)
    except InputError as exc:
        _fail(exc, exc.exit_code)
    except (ValueError, UnicodeDecodeError, OSError):
        _fail(SchemaOutputError("Result JSON does not match schema"), ExitCode.SCHEMA_ERROR)


@app.command()
def evaluate(
    samples: Annotated[Path, typer.Argument(exists=False, file_okay=False)] = Path("samples"),
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Compare committed outputs with ground truth using deterministic metrics."""
    try:
        if not samples.is_dir():
            raise InputError(f"Samples directory does not exist: {samples}")
        report = evaluate_samples(samples)
        _emit_json(json.dumps(report, indent=2, sort_keys=True), output)
        typer.echo(
            f"evaluated {report['fixture_count']} fixtures; "
            f"schema rate={report['schema_validity']['rate']}",
            err=True,
        )
    except (InputError, OSError, json.JSONDecodeError) as exc:
        code = exc.exit_code if isinstance(exc, DDEError) else ExitCode.INPUT_ERROR
        _fail(exc, code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
