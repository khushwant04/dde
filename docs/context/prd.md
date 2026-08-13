# Product Requirements Document (PRD)

**Status: Planned.** This PRD defines the intended challenge submission; it does not describe implemented behavior.

## Product statement

The Document Data Extractor takes an invoice or receipt in PDF, image, or UTF-8 text form and returns schema-valid JSON containing normalized fields and line items, deterministic validation results, and an explicit human-review decision.

## Problem

Business documents vary in layout and input quality. OCR or a language model can extract plausible values but may omit fields, invent values, or accept inconsistent arithmetic. Reviewers need a small, runnable agent that combines semantic document understanding with strict output and code-based checks.

## Users

- **Primary:** challenge reviewer running sample documents from the repository.
- **Secondary:** developer integrating structured extraction into a workflow.
- **Future:** operator hosting a stateless extraction API in Docker or Kubernetes.

## Goals

1. Demonstrate end-to-end extraction for PDF, image, and text inputs.
2. Normalize different invoice and receipt layouts into one stable result envelope.
3. Detect invalid dates and inconsistent money calculations deterministically.
4. Return missing values as `null` and flag uncertain or invalid records for review.
5. Make setup, execution, and evaluation reproducible from the root README.

## MVP scope

- Python CLI.
- `.pdf`, `.png`, `.jpg`, `.jpeg`, and `.txt` inputs.
- Invoice and receipt document types.
- At least two visibly different layouts; target two invoice and two receipt layouts.
- Multimodal structured extraction through one tested provider.
- Strict schema validation and at most one schema-repair attempt.
- Decimal/date business-rule validation.
- Single-document, batch, validation-only, and evaluation commands.
- Synthetic redistributable fixtures, ground truth, and committed example outputs.
- Docker image for a reproducible CLI run after the native CLI is complete.

## Post-core hosting scope

- A minimal synchronous HTTP adapter around the same application service.
- A stateless Docker runtime.
- Kubernetes Deployment, Service, ConfigMap, and example Secret manifests.
- Health/readiness endpoints and documented resource/security settings.

Kubernetes is not a prerequisite for the extractor MVP or the scored three-minute demo. It must not delay extraction, validation, tests, fixtures, or README reproducibility.

## Non-goals

- Arbitrary document types, handwriting, and credit notes.
- Fine-tuning, RAG, embeddings, or a vector database.
- Open-ended multi-agent orchestration.
- Automatic correction of source values.
- User accounts, durable job storage, or a relational database.
- Production autoscaling, high availability, or multi-region deployment.
- A web UI before all core acceptance criteria pass.

## Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| `FR-001` | Accept supported PDF, image, and UTF-8 text files. | Must |
| `FR-002` | Reject unsupported, corrupt, encrypted, empty, or oversized input predictably. | Must |
| `FR-003` | Extract document type, identifier, vendor, dates, currency, totals, and line items without fabricating missing values. | Must |
| `FR-004` | Produce one versioned, schema-valid JSON envelope across all layouts. | Must |
| `FR-005` | Validate line amounts, subtotal, total, dates, currency, and unsupported negative values using code. | Must |
| `FR-006` | Preserve extracted source values when a business rule fails and emit issue codes. | Must |
| `FR-007` | Set validation status and `review_required` from deterministic issues. | Must |
| `FR-008` | Process all supported files in a directory. | Must |
| `FR-009` | Revalidate saved JSON without calling the model. | Must |
| `FR-010` | Evaluate fixture outputs against committed ground truth. | Must |
| `FR-011` | Package the CLI as a non-root Docker image. | Should |
| `FR-012` | Expose the same extraction service through a hosted HTTP adapter. | Could |
| `FR-013` | Supply minimal Kubernetes manifests for the hosted adapter. | Could |

## Quality requirements

- Monetary calculations use decimal arithmetic, not binary floating point.
- Unknown fields are forbidden by the output schema.
- Model output never supplies trusted validation metadata.
- Offline unit and pipeline tests run without an API key.
- Diagnostics never print API keys and should avoid full document contents.
- Documents are treated as untrusted data, including embedded prompt-injection text.
- The default demo completes in a few minutes using repository fixtures.

## Success criteria

The MVP succeeds when:

- Every supported format has a tested loader path.
- At least two distinct layouts produce the same valid envelope.
- A deliberately incorrect invoice emits `TOTAL_MISMATCH` without changing its printed total.
- Missing values remain `null`.
- Offline tests pass without provider credentials.
- The documented extraction and evaluation commands run from a clean environment.
- Sample documents, ground truth, outputs, tradeoffs, and known failures are committed.

Hosted packaging succeeds separately when the container and Kubernetes checks in the deployment requirements pass.

## Challenge traceability

The brief contains resume-specific wording in the universal rubric. This project interprets the 30-point category as working end-to-end DDE functionality and the 25-point category as extraction approach and model choice because the brief says functionality is judged against the chosen agent.

| Weight | DDE evidence |
|---:|---|
| 30 | Runnable PDF/image/text pipeline, varied layouts, strict JSON, mismatch detection, and batch demo. |
| 25 | Multimodal structured extraction, bounded repair, deterministic validators, and measured fixture performance. |
| 20 | Typed modules, provider boundary, domain errors, tests, linting, and type checking. |
| 15 | Exact setup, environment variables, copy-paste demo, expected output, and troubleshooting. |
| 10 | Explicit scope, model/dependency rationale, privacy/cost notes, known failures, and next improvements. |

## Product risks

- Model/API access may fail or change; verify it before implementation proceeds.
- OCR quality and complex tables may reduce extraction accuracy.
- Locale-specific currency and date formats may be ambiguous.
- Infrastructure work may consume challenge time without improving core scoring.
- A small synthetic fixture set demonstrates behavior but does not prove production accuracy.