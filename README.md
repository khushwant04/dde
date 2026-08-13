# Document Data Extractor

[![CI](https://github.com/khushwant04/dde/actions/workflows/ci.yml/badge.svg)](https://github.com/khushwant04/dde/actions/workflows/ci.yml)

A framework-free Python 3.12 agent that turns PDF, PNG, JPEG, or UTF-8 text invoices/receipts into strict JSON plus deterministic validation results.

- **Rooman 24-Hour AI Agent Challenge:** Data & Documents — **Document Data Extractor (Advanced)**
- **Release:** [`v0.1.0`](https://github.com/khushwant04/dde/releases/tag/v0.1.0)
- **Model target:** Azure AI Foundry `gpt-5.6-sol` through the OpenAI Responses API

## Project assessment

> **One job:** take a messy invoice or receipt and return source-grounded, schema-valid JSON with a trusted review decision.

```text
document -> guarded loader -> LLM structured extraction -> strict Pydantic model
                                                       -> deterministic validation -> JSON
```

The model handles visual/semantic extraction; Python owns input safety, parsing, arithmetic, dates, issue severity, and `review_required`. This implements the challenge's Input → Think → Act → Output loop without an unnecessary autonomous-agent framework.

This assessment maps to the Rooman brief supplied directly for the selection round; no canonical public brief URL was provided. Detailed requirements remain owned by the [PRD](docs/context/prd.md), and implementation is authoritative.

### Expected-capability evidence

| Challenge capability | Implemented evidence |
|---|---|
| Read PDF, image, and text | Content-aware `.pdf`, `.png`, `.jpg`, `.jpeg`, and strict UTF-8 `.txt` loaders; PDFs include native text and bounded renders. |
| Extract dates, amounts, lines, and IDs | A strict schema covers identity, vendor/customer, dates, currency, line items, subtotal, discount, tax, shipping, and total. |
| Return validated JSON | Unknown fields are forbidden; provider values become strict Pydantic types in a versioned envelope. |
| Add sanity checks | Decimal/date/currency rules detect line, subtotal, total, duplicate, negative, and reversal issues without rewriting source values. |
| Handle multiple layouts | Seven valid synthetic fixtures cover seven layouts plus one corrupt-input fixture. |

### Agent-specific deliverables

| Deliverable | Evidence |
|---|---|
| Varied documents | [`samples/documents/`](samples/documents) |
| Extracted JSON | [`samples/outputs/`](samples/outputs) |
| Separate expected data | [`samples/ground_truth/`](samples/ground_truth) |
| Validation and failures | [Validation contract](docs/context/technical-requirements.md#validation-contract) and [implemented limitations](docs/context/prd.md#implemented-limitations) |
| Evaluation summary | [`samples/evaluation-summary.json`](samples/evaluation-summary.json) |

## Reviewer quick start

Prerequisites: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/khushwant04/dde.git
cd dde
uv sync --frozen
uv run dde doctor

uv run dde extract samples/documents/invoice_a.pdf \
  --provider fake --output /tmp/dde-clean.json

# Expected exit 2: printed total remains 270.00 and TOTAL_MISMATCH is emitted
uv run dde extract samples/documents/invoice_mismatch.pdf \
  --provider fake --strict --output /tmp/dde-mismatch.json

uv run dde evaluate samples --output /tmp/dde-evaluation.json
```

Expected: `invoice_a.pdf` returns ID `INV-20491` with status `pass`; the mismatch preserves `270.00`; evaluation processes 7/7 valid fixtures with 7/7 schema validity.

`--provider fake` proves deterministic loading, schemas, validation, CLI behavior, and reproducibility. It is **not live-model accuracy evidence**.

## Real-provider configuration

DDE supports API-key and Azure identity authentication. Azure identity additionally requires the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) for local `az login` (or another `DefaultAzureCredential` source).

```bash
# API key
export OPENAI_BASE_URL='https://YOUR-ENDPOINT/openai/v1/'
export OPENAI_API_KEY='YOUR-KEY'
export DDE_MODEL='YOUR-MODEL-OR-DEPLOYMENT'
export DDE_AUTH_MODE='api_key'

# Or Azure identity
az login
export OPENAI_BASE_URL='https://YOUR-RESOURCE.openai.azure.com/openai/v1/'
export DDE_MODEL='gpt-5.6-sol'
export DDE_AUTH_MODE='azure_identity'
unset OPENAI_API_KEY

uv run dde doctor
uv run dde extract samples/documents/invoice_a.pdf --output /tmp/dde-live.json
```

The provider receives the source filename, media type, available document text, and source or rendered images. Review provider retention, region, cost, and privacy terms before use. See the [full configuration and CLI contract](docs/context/technical-requirements.md#configuration).

## Approach and evidence

- One primary structured extraction call is made; schema failure permits at most one schema-only repair call, so the happy path uses one call and the maximum is two.
- `responses.parse` targets strict Pydantic models; source-optional fields are required-but-nullable.
- Python `Decimal` and date rules—not the model—produce trusted validation metadata.
- Validators preserve printed values and report inconsistencies instead of silently correcting them.
- Exact balanced reversals are informational; unmatched negatives remain errors.

The committed fake-provider summary reports 7/7 processing/schema validity, 98/98 exact header comparisons, 35/35 decimals, line-item F1 `1.0`, 3/3 expected issue detections, and zero hallucinations. These fixture-derived values demonstrate the harness, not model accuracy.

Three authorized private-invoice runs are **author-reported private spot checks**, not reviewer-verifiable public evidence. Their sources/results remain outside the repository and release. They support only a limited compatibility claim; a representative public live-model benchmark remains future work. The [evaluation requirements](docs/context/evaluation-requirements.md) define these evidence boundaries.

## Rubric evidence

The table maps the supplied universal rubric to the selected Document Data Extractor; it is evidence, not a self-awarded score.

| Weight | Reviewer-visible evidence |
|---:|---|
| 30 — Working end to end | Runnable PDF/image/text pipeline, strict JSON, varied layouts, preserved mismatch values, batch/revalidation commands, stable exits, and released artifacts. |
| 25 — Approach/model | Azure `gpt-5.6-sol`, multimodal Responses extraction, strict parsing, bounded repair, and deterministic business rules. |
| 20 — Code quality | Typed module boundaries, domain errors, exact lockfile, Ruff, strict mypy, 94 offline tests, 91% branch coverage, and CI. |
| 15 — README/reproducibility | Copy-paste demo, provider setup, expected results, public samples/outputs, clean-clone rehearsal, and checksummed release. |
| 10 — Tradeoffs/reasoning | Framework/model rationale, privacy/cost boundaries, honest evidence labels, limitations, and deferred infrastructure. |

## Tradeoffs and limitations

- Direct SDK integration is smaller and more testable than an agent framework for a fixed workflow with two calls maximum.
- Model vision avoids a host OCR binary but depends on document/image quality.
- Strict validation favors reliable review signals over automatic correction.
- Supported document types are invoices and receipts; purchase orders, full credit-note workflows, handwriting, and password-protected PDFs are outside `v0.1.0`.
- Ambiguous dates remain `null`; the currency allowlist is intentionally bounded.
- Docker, HTTP API, Kubernetes, databases, UI, and agent frameworks were deferred in favor of the scored core.

Full scope and known failures: [PRD](docs/context/prd.md) and [technical requirements](docs/context/technical-requirements.md).

## Verification and documentation

CI runs frozen dependency sync, lock validation, Ruff, strict mypy, 94 non-live tests with branch coverage, and package builds. Current release evidence includes 91% branch-aware coverage, byte-reproducible fixtures, clean wheel installation, and privacy-inspected archives. Artifacts and checksums are in [`v0.1.0`](https://github.com/khushwant04/dde/releases/tag/v0.1.0).

- [Documentation index](docs/context/README.md)
- [Product requirements and challenge traceability](docs/context/prd.md)
- [Architecture decisions](docs/context/ard.md)
- [Setup, schemas, validation, configuration, CLI, and exits](docs/context/technical-requirements.md)
- [Fixtures, metrics, tests, and evidence policy](docs/context/evaluation-requirements.md)
- [Planned deployment requirements](docs/context/deployment-requirements.md)
- [Implementation sequence and three-minute demo](docs/implementation-blueprint.md)

## License

Licensed under the [MIT License](LICENSE).
