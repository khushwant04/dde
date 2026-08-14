# Document Data Extractor

[![CI](https://github.com/khushwant04/dde/actions/workflows/ci.yml/badge.svg)](https://github.com/khushwant04/dde/actions/workflows/ci.yml)

A Python 3.12 document-extraction application that turns PDF, PNG, JPEG, UTF-8 text, CSV, or XLSX invoices, receipts, purchase orders, and credit notes into strict JSON plus deterministic validation results.

- **Rooman 24-Hour AI Agent Challenge:** Data & Documents — **Document Data Extractor (Advanced)**
- **Release:** [`v0.1.0`](https://github.com/khushwant04/dde/releases/tag/v0.1.0)
- **Model target:** Azure AI Foundry `gpt-5.6-sol` through the OpenAI Responses API

## Project assessment

> **One job:** take a messy financial document and return source-grounded, schema-valid JSON with a trusted review decision.

```text
document -> guarded loader -> LLM structured extraction -> strict Pydantic model
                                                       -> deterministic validation -> JSON
```

The model handles visual/semantic extraction; Python owns input safety, parsing, arithmetic, dates, issue severity, and `review_required`. This implements the challenge's Input → Think → Act → Output loop without an unnecessary autonomous-agent framework.

This assessment maps to the Rooman brief supplied directly for the selection round; no canonical public brief URL was provided. Detailed requirements remain owned by the [PRD](docs/context/prd.md), and implementation is authoritative.

### Expected-capability evidence

| Challenge capability | Implemented evidence |
|---|---|
| Read PDF, image, text, and spreadsheets | Content-aware PDF/PNG/JPEG, strict UTF-8 TXT/CSV, and guarded `.xlsx` loaders; PDFs include native text and bounded renders. Legacy `.xls` and `.ods` are rejected. |
| Extract dates, amounts, lines, and IDs | A strict schema covers identity, vendor/customer, dates, currency, line items, subtotal, discount, tax, shipping, and total. |
| Return validated JSON | Unknown fields are forbidden; provider values become strict Pydantic types in a versioned envelope. |
| Add sanity checks | Decimal/date/currency rules detect line, subtotal, total, duplicate, negative, and reversal issues without rewriting source values. |
| Handle multiple layouts | Eleven valid synthetic fixtures cover eleven layouts plus one corrupt-input fixture. |

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

Expected: `invoice_a.pdf` returns ID `INV-20491` with status `pass`; the mismatch preserves `270.00`; evaluation processes 11/11 valid fixtures with 11/11 schema validity.

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

## Docker

The multi-stage image uses an immutable Python 3.12.14 slim base, locked runtime-only dependencies, a deny-by-default build context, and fixed user `10001:10001`.

```bash
docker build --pull -t dde:local .
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,src="$PWD/samples",dst=/work,readonly \
  dde:local python -m dde extract /work/documents/invoice_c.txt \
  --provider fake --fake-response-dir /work/fake_responses
```

The build may need network access to obtain the pinned base and locked packages; the shown runtime check is offline. Local evidence covers linux/amd64 only and is not a vulnerability-scan, signed-image, SBOM, multi-architecture, or production-readiness claim. See [deployment requirements](docs/context/deployment-requirements.md) for the complete image and probe checks.

## Hosted API

With provider configuration set as above, run the synchronous adapter locally:

```bash
uv run uvicorn dde.api:app --host 127.0.0.1 --port 8080
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/readyz
curl --fail -F 'file=@samples/documents/invoice_a.pdf' \
  http://127.0.0.1:8080/v1/extractions
```

Health and readiness never call the provider. Multipart request bytes, document bytes, concurrent workers, and client wait time are separately bounded. Excess concurrency returns `429`; response timeout returns `504`, but cannot forcibly cancel a running provider call, so its slot and temporary workspace remain occupied until worker cleanup. The adapter is stateless and tested offline, but has no authentication, TLS termination, or distributed rate limiting and must not be exposed directly to the internet.

## Approach and evidence

- One primary structured extraction call is made; schema failure permits at most one schema-only repair call, so the happy path uses one call and the maximum is two.
- `responses.parse` targets strict Pydantic models; source-optional fields are required-but-nullable.
- Python `Decimal` and date rules—not the model—produce trusted validation metadata.
- Validators preserve printed values and report inconsistencies instead of silently correcting them.
- Exact balanced reversals are informational; unmatched negatives remain errors.

The committed fake-provider summary reports 11/11 processing/schema validity, 176/176 exact header comparisons, 55/55 decimals, line-item F1 `1.0`, and code-level validation issue precision/recall/F1 of `1.0` (4 true positives, zero false positives, zero false negatives), with zero hallucinations. It also breaks processing and schema validity down by format, layout, and all four document types. These fixture-derived values demonstrate the harness, not model accuracy.

Three authorized private-invoice runs are **author-reported private spot checks**, not reviewer-verifiable public evidence. Their sources/results remain outside the repository and release. They support only a limited compatibility claim; a representative public live-model benchmark remains future work. The [evaluation requirements](docs/context/evaluation-requirements.md) define these evidence boundaries.

## Rubric evidence

The table maps the supplied universal rubric to the selected Document Data Extractor; it is evidence, not a self-awarded score.

| Weight | Reviewer-visible evidence |
|---:|---|
| 30 — Working end to end | Runnable PDF/image/text pipeline, strict JSON, varied layouts, preserved mismatch values, batch/revalidation commands, stable exits, and released artifacts. |
| 25 — Approach/model | Azure `gpt-5.6-sol`, multimodal Responses extraction, strict parsing, bounded repair, and deterministic business rules. |
| 20 — Code quality | Typed module boundaries, domain errors, exact lockfile, Ruff, strict mypy, branch-aware offline tests, and CI; published release evidence is linked below. |
| 15 — README/reproducibility | Copy-paste demo, provider setup, expected results, public samples/outputs, clean-clone rehearsal, and checksummed release. |
| 10 — Tradeoffs/reasoning | Framework/model rationale, privacy/cost boundaries, honest evidence labels, limitations, and deferred infrastructure. |

## Tradeoffs and limitations

- Direct SDK integration is smaller and more testable than an agent framework for a fixed workflow with two calls maximum.
- Model vision avoids a host OCR binary but depends on document/image quality.
- Strict validation favors reliable review signals over automatic correction.
- Supported document types in `v0.1.0` are invoices and receipts; purchase orders, full credit-note workflows, handwriting, and password-protected PDFs were outside that release.
- Current credit-note validation supports coherent positive-magnitude or negative-signed monetary profiles; mixed/ambiguous signs require review, and no printed value is corrected.
- The purchase-order schema is intentionally flat and omits enterprise approval, fulfillment, and complex terms workflows.
- XLSX formulas are never executed; formula text and available cached values are labeled separately, missing caches and skipped hidden sheets require review, and cached values may be stale.
- Charts, comments, drawings, pivots, and exact spreadsheet visual formatting are not canonicalized; active content and external relationships are rejected, and `.xls`/`.ods` remain unsupported.
- Ambiguous dates remain `null`; the currency allowlist is intentionally bounded.
- The synchronous API is stateless and bounded but has no authentication, TLS termination, durable queue, or distributed rate limiting; a `504` does not forcibly cancel the active provider worker.
- Minimal Kubernetes templates are implemented; cluster production readiness, databases, UI, and agent frameworks remain deferred.

Full scope and known failures: [PRD](docs/context/prd.md) and [technical requirements](docs/context/technical-requirements.md).

## Verification and documentation

CI runs frozen dependency sync, lock validation, Ruff, strict mypy, non-live tests with branch coverage, and package builds. Published `v0.1.0` evidence includes 94 offline tests, 91% branch-aware coverage, byte-reproducible fixtures, clean wheel installation, and privacy-inspected archives. Artifacts and checksums are in [`v0.1.0`](https://github.com/khushwant04/dde/releases/tag/v0.1.0).

- [Documentation index](docs/context/README.md)
- [Product requirements and challenge traceability](docs/context/prd.md)
- [Architecture decisions](docs/context/ard.md)
- [Setup, schemas, validation, configuration, CLI, and exits](docs/context/technical-requirements.md)
- [Fixtures, metrics, tests, and evidence policy](docs/context/evaluation-requirements.md)
- [Hosted API and deployment requirements](docs/context/deployment-requirements.md)
- [Implementation sequence and three-minute demo](docs/implementation-blueprint.md)

## License

Licensed under the [MIT License](LICENSE).
