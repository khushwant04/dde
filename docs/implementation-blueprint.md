# DDE Implementation Blueprint

**Status: Native core, synchronous HTTP adapter, and secure Docker image implemented.** Stages 0-7 and the API portion of stage 8 are represented by the current CLI/API/image, guarded loaders, provider adapters, validators, fixtures, evaluator, tests, runnable documentation, and authorized private Azure spot checks. Private live artifacts are intentionally excluded from the repository and do not constitute a representative accuracy benchmark. The minimal Kubernetes template portion of stage 8 is implemented; cluster production readiness remains unverified. This document owns delivery sequence and time allocation only; requirements and design live in the [context document set](context/README.md).

## Context references

- [Product Requirements](context/prd.md)
- [Architecture Requirements and Decisions](context/ard.md)
- [Technical Requirements](context/technical-requirements.md)
- [Deployment Requirements](context/deployment-requirements.md)
- [Evaluation Requirements](context/evaluation-requirements.md)

## Delivery principles

1. Make one document work end to end before adding formats or layouts.
2. Freeze schema and issue codes before prompt tuning.
3. Keep provider calls behind a fakeable boundary.
4. Trust code—not the model—for arithmetic, dates, and review status.
5. Do not start Docker until native core checks pass.
6. Do not start Kubernetes while any higher-value challenge requirement is failing.
7. Freeze features with enough time for a clean reviewer rehearsal.

## Implementation sequence

### 0. Provider spike

- Create the Python environment.
- Send one text and one document image to the selected model.
- Verify structured response support.
- Record the exact package and model versions.

**Exit:** one image returns data that can be parsed into a temporary typed model.

### 1. Contracts and fixtures

- Implement result, extracted-document, line-item, validation, and issue models.
- Create the first clean invoice and its hand-authored ground truth.
- Add domain errors and configuration parsing.

**Exit:** hand-authored expected JSON passes schema tests.

### 2. Ingestion

- Implement content-aware guards.
- Add text, image, and PDF loaders.
- Extract native PDF text and render bounded page images.
- Test unsupported, empty, corrupt, and oversized inputs.

**Exit:** every supported core format returns canonical loaded content or a typed error.

### 3. Structured extraction

- Write the injection-resistant extraction prompt.
- Implement the model protocol, real adapter, and fake adapter.
- Parse structured output and allow one schema-repair call.
- Preserve nulls and line-item order.

**Exit:** two different layouts produce schema-valid extracted documents.

### 4. Deterministic validation

- Implement decimal and date checks.
- Derive status and review decision from issue severity.
- Ensure validators never mutate extracted source values.
- Add the deliberately incorrect-total fixture.

**Exit:** the mismatch is detected by issue code and its printed total remains unchanged.

### 5. CLI and batch flow

- Add `extract`, `batch`, `validate`, and `evaluate` commands.
- Separate JSON output from diagnostics.
- Implement documented exit behavior and strict mode.

**Exit:** core commands work through the application service with fake-provider tests.

### 6. Evaluation and hardening

- Complete the fixture matrix and ground truth.
- Implement field, decimal, line-item, schema, and issue-detection metrics.
- Run the live provider evaluation and retain all failures.
- Add lint, type, unit, pipeline, and clean-environment checks.

**Exit:** the evaluation summary is reproducible and all core completion gates pass.

### 7. Docker packaging

- **Implemented:** locked runtime, deny-by-default `.dockerignore`, multi-stage build, and fixed user `10001:10001`.
- **Verified locally on linux/amd64:** CLI help, offline fake extraction/revalidation, runtime-only contents, no embedded provider configuration, hosted probes, and clean termination under network-none/read-only/capability-dropped controls.

**Exit:** Docker packaging acceptance criteria pass without changing domain behavior. Vulnerability scanning, signing/SBOM publication, and multi-architecture evidence remain outside this result.

### 8. Hosted API and Kubernetes

This is post-core work.

- **Implemented:** thin synchronous HTTP adapter, health/readiness endpoints, bounded multipart reception, concurrency/deadline handling, and temporary cleanup.
- **Implemented locally:** run the same fixed-non-root image in hosted mode and probe it without external network access.
- **Implemented:** minimal ConfigMap, example Secret, Deployment, Service, and deployment notes.
- **Verified in an isolated temporary cluster:** API-server validation, pinned-image rollout, ClusterIP probes, runtime security, sanitized unsupported-upload handling, and idle SIGTERM recovery.
- **Unverified:** configured-provider extraction, active-request shutdown, high availability, and production readiness.

**Exit:** API behavior is independently gated; remaining container and cluster hosting gates pass only when verified as defined in deployment requirements.

### 9. Reviewer rehearsal and freeze

- Start from a clean checkout and follow only the root README.
- Run the three-minute demo.
- Verify sample outputs, model/config notes, limitations, and tradeoffs.
- Stop feature work and preserve submission buffer.

## Twenty-four-hour allocation

| Hours | Focus | Required checkpoint |
|---:|---|---|
| 0-1 | Environment and provider spike | Structured image response works. |
| 1-3 | Schemas, errors, initial fixtures | Expected JSON parses. |
| 3-6 | Input guards and loaders | PDF/image/text tests pass. |
| 6-9 | Provider and extraction pipeline | Two layouts produce valid structure. |
| 9-12 | Deterministic validators | Happy and mismatch tests pass. |
| 12-14 | CLI and batch behavior | Stable commands and exit behavior. |
| 14-17 | Fixtures and evaluator | Metrics summary is generated. |
| 17-19 | Failure handling and offline tests | Core completion gate passes. |
| 19-20 | Docker, if core remains green | Container CLI smoke test passes. |
| 20-21 | Hosted/Kubernetes stretch or core fixes | No core regression. |
| 21-23 | README and clean rehearsal | Reviewer flow passes from scratch. |
| 23-24 | Submission buffer | Final working revision is pushed. |

Kubernetes is deliberately limited to at most one hour during the challenge unless the full core is already complete. It may be finished after the challenge only if late commits are allowed; otherwise unverified manifests must not be presented as implemented.

## Risk cutoffs

- Provider unavailable at hour 2: switch the provider/model, not the architecture.
- Scanned-PDF path unstable at hour 8: document the tested limit and protect clean PDF/image paths.
- Accuracy weak at hour 16: improve prompt and fixtures; do not add UI or orchestration.
- Core gate failing at hour 19: skip hosted API and Kubernetes implementation.
- Any README command fails after hour 21: fix reproducibility before all optional work.

## Commit checkpoints

Suggested small working commits:

1. project scaffold and schema;
2. fixtures and loaders;
3. provider extraction;
4. deterministic validation;
5. CLI and batch flow;
6. evaluation and tests;
7. Docker packaging;
8. optional hosted API and Kubernetes manifests;
9. documentation and final hardening.

## Three-minute demo

1. Extract a clean table-style PDF invoice.
2. Extract a visually different receipt image into the same result envelope.
3. Extract the incorrect-total invoice and show `TOTAL_MISMATCH` without altered source values.
4. Run fixture evaluation and show schema, field, line-item, and issue-detection results.

Docker may be used for reproducibility. Kubernetes should be mentioned only after the core behavior is demonstrated.
