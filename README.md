# Document Data Extractor

[![CI](https://github.com/khushwant04/dde/actions/workflows/ci.yml/badge.svg)](https://github.com/khushwant04/dde/actions/workflows/ci.yml)

DDE is a framework-free Python 3.12 CLI that extracts strict invoice/receipt JSON from PDF, PNG, JPEG, and UTF-8 text through an OpenAI Responses-compatible provider, then validates dates and arithmetic deterministically.

## Quick start

Prerequisites: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run dde doctor
uv run dde extract samples/documents/invoice_a.pdf --provider fake
uv run dde extract samples/documents/invoice_mismatch.pdf --provider fake --strict
uv run dde evaluate samples
```

`--provider fake` is a deterministic fixture smoke path, not live-model accuracy evidence. The mismatch command preserves the printed total, emits `TOTAL_MISMATCH`, and exits 2 because review is required.

## Documentation

- [Documentation index](docs/context/README.md)
- [Setup, provider configuration, schemas, validation, CLI, and exits](docs/context/technical-requirements.md)
- [Architecture and design decisions](docs/context/ard.md)
- [Fixtures, metrics, tests, and evidence policy](docs/context/evaluation-requirements.md)
- [Product scope, limitations, and success criteria](docs/context/prd.md)
- [Implementation sequence and deferred work](docs/implementation-blueprint.md)

## Status

The native CLI core, synthetic fixtures, evaluator, and tests are implemented. The Azure adapter has been exercised against authorized private invoices, whose sources and results remain outside the repository and package; those spot checks establish compatibility, not general accuracy. Docker, HTTP API, Kubernetes, databases, and agent frameworks are not implemented and remain optional post-core work.
## License

Licensed under the [MIT License](LICENSE).
