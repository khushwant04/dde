# Evaluation Requirements

**Status: Planned.** No fixtures, tests, or measured results exist yet. Do not report planned metrics as achieved results.

## Evaluation goals

- Prove that each supported input format reaches a schema-valid result or a documented failure.
- Demonstrate layout variation rather than testing one template repeatedly.
- Measure extraction against committed ground truth.
- Verify deterministic validators independently from the model.
- Keep offline tests reproducible without credentials or network access.
- Supply reviewer-visible evidence for the challenge rubric.

## Fixture set

Create at least eight redistributable synthetic fixtures:

| ID | Format | Layout | Required evidence |
|---|---|---|---|
| `invoice_a` | digital PDF | traditional table | Clean invoice happy path. |
| `invoice_b` | PNG | modern two-column | Different field placement and visual structure. |
| `invoice_c` | TXT | compact text | Text-loader and normalization path. |
| `invoice_d` | scanned PDF | table | Visual-only PDF path. |
| `receipt_a` | JPEG | narrow thermal | Receipt fields and short item rows. |
| `receipt_b` | PDF | wide retail | Second receipt layout. |
| `invoice_mismatch` | PDF | table | Printed total is incorrect and must remain unchanged while being flagged. |
| `bad_input` | corrupt or unsupported file | n/a | Stable rejection and error code. |

Across the valid fixtures include:

- multiple date formats;
- at least two currencies;
- absent optional fields;
- one absent identifier;
- multi-line item descriptions;
- discounts or tax where unambiguous;
- one arithmetic mismatch;
- layouts with fields in different positions.

Generate fixtures locally and avoid confidential, personal, or copyrighted business documents.

## Fixture artifacts

```text
samples/
|-- documents/
|-- ground_truth/
|-- outputs/
`-- evaluation-summary.json
```

Every valid document has one ground-truth JSON file. Every reviewer demo document has one committed example output produced by the declared tested model. Ground truth and actual output must never be stored in the same file.

## Metrics

The evaluator reports counts and rates, not only a single aggregate score:

1. **Processing success:** supported documents yielding a result envelope.
2. **Schema validity:** outputs accepted by the strict result schema.
3. **Header-field exact match:** normalized document type, ID, vendor, date, currency, subtotal, tax, discount, shipping, and total.
4. **Decimal accuracy:** exact decimal comparison after normalization.
5. **Line-item precision/recall/F1:** compare normalized tuples of description, quantity, unit price, and amount while preserving duplicate rows.
6. **Validation detection:** expected issue codes found for deliberate failure fixtures.
7. **Hallucination count:** non-null values where ground truth is null.
8. **Format/layout breakdown:** results grouped by PDF/image/text and layout family.

Any fuzzy description comparison must publish its normalization and threshold. Do not let fuzzy matching hide wrong quantities or amounts.

## Test layers

### Unit tests

Must cover:

- supported/unsupported media detection;
- byte, page, dimension, and empty-input guards;
- decimal parsing and tolerance boundaries;
- valid, invalid, leap-day, and ambiguous dates;
- every validation issue code;
- status and review decision derivation;
- exit and HTTP error mappings;
- filename sanitization and temporary-file cleanup.

### Pipeline tests

Use the fake model adapter to cover:

- valid extraction;
- missing optional fields;
- unknown-field rejection;
- malformed JSON repaired once;
- output invalid after repair;
- provider failure;
- arithmetic mismatch preserved and reported;
- embedded prompt-injection text treated as document content.

These tests run without an API key or network.

### Live fixture evaluation

A live provider run generates actual outputs and the metrics summary. It is explicit and opt-in because it uses network, credentials, time, and potentially money. Record:

- UTC timestamp;
- provider and exact model ID;
- application revision;
- fixture-set version or digest;
- per-document latency when available;
- failures without secret or full-provider-payload leakage.

### Packaging tests

After core tests pass:

- build the Docker image from a clean checkout;
- run CLI help and offline validation in the container;
- run one live sample when credentials are intentionally supplied;
- test API health and one extraction;
- validate Kubernetes manifests and run a cluster smoke test when available.

Deployment-specific checks are owned by [Deployment Requirements](deployment-requirements.md).

## Required commands

The final repository must expose documented equivalents of:

```bash
pytest
python -m dde evaluate samples
python -m dde extract samples/documents/invoice_a.pdf
python -m dde extract samples/documents/invoice_mismatch.pdf --strict
```

Add lint, format, and type-check commands after tools are selected and pinned. The README must not list a command that has not been executed successfully in the final environment.

## Core completion gate

Core behavior is complete only when:

- all unit and fake-provider pipeline tests pass;
- all valid committed example outputs parse against the result schema;
- PDF, image, and text paths are represented;
- at least two visibly different layouts map to the same schema;
- `invoice_mismatch` emits `TOTAL_MISMATCH` and preserves its source total;
- missing fields remain `null` in tested output;
- corrupt/unsupported input produces the documented error behavior;
- the evaluator produces a machine-readable and human-readable summary;
- a fresh-environment reviewer rehearsal succeeds using only README instructions.

## Evidence mapped to challenge scoring

| Area | Evidence |
|---|---|
| End-to-end functionality | Three input formats, varied layouts, JSON outputs, mismatch fixture, and batch/evaluation transcript. |
| Approach/model choice | Architecture rationale, exact model record, deterministic validation tests, and metric breakdown. |
| Code quality | Offline test suite, type/lint checks, provider fake, typed errors, and clean module boundaries. |
| Reproducibility | Clean-environment installation and copy-paste reviewer demo. |
| Tradeoffs | Documented limitations, fixture scope, model cost/privacy, failed cases, and deferred infrastructure. |

## Result-reporting policy

- Label all pre-implementation targets as planned.
- Report fixture-set performance, not general document accuracy.
- Preserve failures in the summary; do not remove difficult fixtures to improve scores.
- Separate deterministic offline test results from nondeterministic live-model results.
- If a check cannot run, state why and identify the next-best verification.
- Never claim Kubernetes production readiness from manifest validation alone.