# Architecture Requirements and Decisions (ARD)

**Status: Native core implemented.** The component boundaries, processing flow, provider adapter, and deterministic validation describe current code. Docker, HTTP, and Kubernetes deployment views remain **Planned**. Implementation is authoritative.

## Architecture drivers

- Finish a reliable challenge MVP within 24 hours.
- Support text and visual documents without host-level OCR binaries.
- Keep language-model behavior behind a testable boundary.
- Avoid an agent framework because the workflow is bounded and deterministic outside model extraction.
- Enforce schema and business rules outside the model.
- Reuse one application service from CLI, tests, and a future hosted API.
- Remain stateless so Docker and Kubernetes packaging stay simple.

## System context

```text
+-------------+      +----------------+      +------------------+
| User / API  |----->| DDE Application|----->| Model Provider   |
+-------------+      +----------------+      +------------------+
       |                      |
       |                      v
       |              +----------------+
       +------------->| JSON Result    |
                      +----------------+
```

One OpenAI Responses-compatible inference endpoint is the only required external runtime service. The default target is Azure AI Foundry `gpt-5.6-sol` version `2026-07-09`, which supports text/image input and the Responses API, so rendered PDF pages and source images can be sent directly to the model. No Document Intelligence service, database, object store, queue, vector store, or agent service is required for the planned MVP.

## Component architecture

```text
+-------------------+
| CLI or HTTP       |
| Transport Adapter |
+-------------------+
          |
          v
+-------------------+
| Application       |
| Extraction Service|
+-------------------+
    |       |       |
    v       v       v
+-------+ +-------+ +----------+
|Loader | |Model  | |Validator |
|Ports  | |Port   | |Rules     |
+-------+ +-------+ +----------+
    |       |            |
    v       v            v
+-------+ +-----------+ +-----------+
| PDF / | | OpenAI    | | Decimal / |
| Image | | Responses | | Date      |
| Text  | | Adapter   | | Rules     |
+-------+ +-----------+ +-----------+
          |
          v
+-------------------+
| Versioned Result  |
| Envelope          |
+-------------------+
```

## Responsibilities

| Component | Responsibility | Must not do |
|---|---|---|
| Transport adapter | Parse CLI/API input, invoke the application service, map errors to exit/status codes. | Contain extraction or validation rules. |
| Input guard | Enforce extension, media type, byte, page, and pixel limits. | Trust filename extension alone. |
| Document loader | Read text, extract native PDF text, and render visual pages. | Interpret business fields. |
| Model adapter | Convert canonical document content into the extraction schema. | Decide trusted validation status. |
| Schema layer | Reject malformed types and unknown fields. | Repair business values. |
| Rule validator | Apply decimal/date invariants and produce issue codes. | Call the model or silently change source values. |
| Result serializer | Produce stable versioned JSON. | Expose secrets or transient SDK objects. |
| Evaluator | Compare actual envelopes with fixture ground truth. | Claim general accuracy from a small sample. |

## Processing flow

1. Transport accepts a file and options.
2. Input guard rejects unsafe or unsupported input.
3. Loader creates canonical content: metadata, available text, and rendered image pages.
4. Model adapter makes one structured extraction call.
5. Schema layer parses the response.
6. If parsing fails, the application may make one constrained repair call using schema errors.
7. If parsing still fails, processing ends with `SCHEMA_FAILED`.
8. Rule validator computes trusted issues from the parsed document.
9. Application returns a versioned result envelope and review decision.

Business-rule mismatches do not trigger model repair. The mismatch is evidence requiring review, not permission to rewrite a printed value.

## Processing states

`RECEIVED -> LOADED -> EXTRACTED -> SCHEMA_VALID -> RULE_VALIDATED -> COMPLETE`

Terminal failure states are `INPUT_REJECTED`, `LOAD_FAILED`, `PROVIDER_FAILED`, and `SCHEMA_FAILED`.

## Architecture decisions

### ADR-001: CLI-first core

**Decision:** Build the CLI and application service before an HTTP server.

**Reason:** The challenge accepts a CLI and scores working behavior over infrastructure polish. The application service remains transport-neutral so an API can be added without duplicating domain logic.

### ADR-002: One multimodal extraction call

**Decision:** Use one multimodal structured-output call rather than separate classifier, OCR, and extraction agents.

**Reason:** Fewer calls reduce latency, cost, failure modes, and implementation time while preserving visual layout understanding.

### ADR-003: PyMuPDF for PDFs

**Decision:** Extract native text and render pages with PyMuPDF.

**Reason:** It handles digital and scanned-PDF paths consistently without requiring Poppler. Rendered page images are supplied when visual context is required.

### ADR-004: Strict schema plus deterministic rules

**Decision:** Use Pydantic for structure and Python `Decimal`/date logic for correctness.

**Reason:** A model is useful for semantic extraction but is not trusted for arithmetic, dates, or final validation status.

### ADR-005: One bounded repair

**Decision:** Allow at most one repair call for JSON/schema errors only.

**Reason:** This provides limited recovery while keeping latency and behavior bounded. Business mismatches are surfaced, not repaired.

### ADR-006: Stateless application

**Decision:** Keep extraction synchronous and stateless for the challenge and initial hosting target.

**Reason:** It permits local, Docker, and Kubernetes execution without a database. Durable jobs and object storage are separate future concerns.

### ADR-007: Direct OpenAI Responses inference with no agent framework

**Decision:** Define a small model protocol, one OpenAI Responses adapter, and one fake test adapter. Configure base URL, model/deployment name, and authentication at runtime; use Azure AI Foundry as the default target. Call the configured inference endpoint directly. Do not use LangChain, LangGraph, AutoGen, Semantic Kernel, Azure AI Agent Service, or another agent runtime for the MVP.

**Reason:** The workflow has fixed states and two model calls at most. Strands was evaluated and is technically compatible through its OpenAI Responses provider, but its loop, built-in tools, state, memory, and multi-agent features would remain unused. Plain Python is easier to explain, test, and finish within the challenge. Provider isolation is still needed for offline tests, but a generalized provider or agent framework is unnecessary.

### ADR-008: Kubernetes after core completion

**Decision:** Treat Kubernetes as a post-core deployment target.

**Reason:** Minimal manifests demonstrate hosting knowledge, but they must not displace higher-value extractor, evaluation, and documentation work.

### ADR-009: Azure AI Foundry with `gpt-5.6-sol`

**Decision:** Use an Azure AI Foundry deployment exposing `gpt-5.6-sol`, configured by endpoint and deployment name. Prefer Microsoft Entra ID/managed identity for hosted execution and allow an API key for local challenge setup.

**Reason:** This is the selected model platform. The Foundry catalog confirms version `2026-07-09` is generally available with text/image input and Chat Completions/Responses support. Deployment-name configuration avoids coupling domain code to an Azure resource name. A startup smoke test still verifies credentials, endpoint behavior, and final strict-schema compatibility.

## Deployment views

### Local and Docker CLI

```text
+----------+      +---------------+      +----------------+
| Document |----->| DDE Container |----->| Model Provider |
+----------+      +---------------+      +----------------+
                       |
                       v
                 +-------------+
                 | JSON Output |
                 +-------------+
```

### Kubernetes-hosted API

```text
+--------+      +---------+      +----------------+      +----------------+
| Client |----->| Service |----->| DDE Deployment |----->| Model Provider |
+--------+      +---------+      +----------------+      +----------------+
                                      |
                                      v
                                +-----------+
                                | Ephemeral |
                                | Workspace |
                                +-----------+
```

The hosted adapter accepts bounded uploads, invokes the same application service, returns JSON, and discards temporary content. Detailed container and manifest requirements belong to [Deployment Requirements](deployment-requirements.md).

## Data boundaries

- Input files and provider responses are untrusted.
- Provider credentials enter through environment or secret injection only; Azure-hosted deployments should prefer managed identity and Workload Identity.
- Temporary files are request-scoped and deleted after processing.
- The MVP does not persist documents or extraction results.
- Logs contain request metadata, timings, and issue codes—not credentials or full document text.

## Architecture constraints

- Core domain modules must not import Typer, FastAPI, or provider-specific CLI concerns.
- Model SDK types must not cross the adapter boundary.
- Validation must be deterministic and runnable without network access.
- Hosted replicas must not depend on local persistent state.
- Infrastructure manifests must use the same image and configuration contract as Docker.

Executable schema, CLI/API, error, and rule details belong to [Technical Requirements](technical-requirements.md). Test evidence belongs to [Evaluation Requirements](evaluation-requirements.md).