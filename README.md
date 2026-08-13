# Document Data Extractor

**Status: Planned — implementation has not started.**

DDE will be a CLI-first agent that converts invoices and receipts from PDF, image, or text into strict JSON and applies deterministic date and arithmetic validation. Docker packaging and a minimal Kubernetes-hosted API are planned after the core extractor is working.

There is currently no runnable application. Planned requirements and decisions are indexed in [docs/context](docs/context/README.md); delivery order is in the [implementation blueprint](docs/implementation-blueprint.md).

## Documentation

- [Product Requirements (PRD)](docs/context/prd.md)
- [Architecture Requirements and Decisions (ARD)](docs/context/ard.md)
- [Technical Requirements](docs/context/technical-requirements.md)
- [Deployment Requirements](docs/context/deployment-requirements.md)
- [Evaluation Requirements](docs/context/evaluation-requirements.md)
- [Implementation Blueprint](docs/implementation-blueprint.md)

Once implementation starts, this README will contain only verified installation, configuration, quick-start, and demo commands. Detailed requirements and tradeoffs will remain under `docs/`.
