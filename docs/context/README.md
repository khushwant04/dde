# DDE Context Documents

**Status: Native core, synchronous HTTP adapter, and secure Docker image implemented.** These documents describe the current CLI/API/image and completed private live-provider spot checks, while minimal Kubernetes templates are implemented and representative live benchmarking remains **Planned**. Code is authoritative when any statement becomes stale.

Each topic has one owner to avoid duplication:

| Document | Owns |
|---|---|
| [Product Requirements (PRD)](prd.md) | Problem, users, scope, functional requirements, success criteria, and challenge rubric. |
| [Architecture Requirements and Decisions (ARD)](ard.md) | System boundaries, component responsibilities, data flow, and architecture decisions. |
| [Technical Requirements](technical-requirements.md) | Runtime, interfaces, schema, CLI/API contracts, validation rules, errors, and security controls. |
| [Deployment Requirements](deployment-requirements.md) | Docker packaging, hosted API, Kubernetes manifests, configuration, operations, and deployment verification. |
| [Evaluation Requirements](evaluation-requirements.md) | Fixtures, ground truth, metrics, tests, and completion gates. |
| [Implementation Blueprint](../implementation-blueprint.md) | Delivery order, time budget, checkpoints, and demo sequence only. |

## Reading order

1. PRD for what must be built and why.
2. ARD for the system shape and major decisions.
3. Technical requirements for executable contracts.
4. Evaluation requirements for proof that the contracts work.
5. Deployment requirements when packaging or hosting the application.
6. Implementation blueprint for sequencing the work.

## Change policy

- Label unimplemented behavior as planned.
- Do not copy requirements between documents; link to the owning document.
- Record architecture choices in the ARD and operational choices in deployment requirements.
- Update evaluation gates whenever a product requirement changes.
- When documentation conflicts with implementation, correct the documentation.