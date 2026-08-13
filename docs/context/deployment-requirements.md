# Deployment Requirements

**Status: Planned.** Docker packaging and Kubernetes hosting do not exist yet. Kubernetes is post-core and must not block the extractor MVP.

## Deployment objectives

1. Reproduce the CLI environment with Docker.
2. Run the same application service behind a minimal HTTP adapter.
3. Deploy the hosted adapter as a stateless Kubernetes workload.
4. Inject model configuration and credentials without rebuilding the image.
5. Provide health checks, resource boundaries, and secure runtime defaults.

## Delivery priority

- **Core gate:** native CLI, extraction, validation, fixtures, evaluation, tests, and README.
- **Packaging gate:** Docker image builds and runs the documented CLI sample.
- **Hosting gate:** HTTP adapter and local container smoke test.
- **Kubernetes gate:** manifests render, validate, deploy, and pass health/extraction smoke tests in an available cluster.

Do not begin Kubernetes work while a core-gate acceptance test is failing.

## Planned repository paths

```text
Dockerfile
.dockerignore
deploy/
`-- k8s/
    |-- deployment.yaml
    |-- service.yaml
    |-- configmap.yaml
    |-- secret.example.yaml
    `-- README.md
```

An optional `ingress.yaml`, `networkpolicy.yaml`, batch `job.yaml`, or Kustomize overlay is stretch work after the minimal manifest set passes.

## Docker requirements

### Image

- Use a pinned Python slim base compatible with the tested runtime; pin the resolved image version and preferably its digest before submission.
- Use a builder stage when compilation/build dependencies would otherwise remain in the runtime image.
- Install only locked runtime dependencies.
- Copy application files after dependency metadata to preserve build cache.
- Run as a dedicated non-root UID/GID.
- Set deterministic Python environment flags and unbuffered output.
- Do not copy `.env`, credentials, test caches, local outputs, or source documents not required for the demo.
- Include OCI labels for source revision and description when practical.

One image should support both transports:

```bash
# CLI mode
podman run --rm -e OPENAI_API_KEY -v "$PWD/samples:/work:ro" dde:local \
  python -m dde extract /work/documents/invoice.pdf

# Hosted mode
podman run --rm -p 8080:8080 -e OPENAI_API_KEY dde:local \
  uvicorn dde.api:app --host 0.0.0.0 --port 8080
```

Equivalent Docker commands must be documented; Podman compatibility is desirable but not a submission requirement.

### Container filesystem and process

- Application code and root filesystem are read-only at runtime where supported.
- Temporary processing uses a bounded writable `/tmp` or mounted ephemeral directory.
- The process handles termination signals and stops accepting requests during shutdown.
- The image contains no provider key or generated secret.
- Logs go to stdout/stderr.

### Docker verification

```bash
docker build -t dde:local .
docker run --rm dde:local python -m dde --help
docker run --rm -p 8080:8080 --env-file .env dde:local
docker inspect dde:local
```

Verify a non-root user, no embedded secret, CLI help, `/healthz`, `/readyz`, one sample extraction, and clean termination.

## Hosted API requirements

The API contract is owned by [Technical Requirements](technical-requirements.md). Deployment-specific constraints are:

- Listen on `0.0.0.0:${PORT:-8080}`.
- Stay stateless; save uploads only in request-scoped temporary storage.
- Enforce upload limits before rendering or provider calls.
- Return health/readiness without making billable model requests.
- Set request and provider timeouts.
- Limit concurrent expensive requests per process until load tests establish safe values.
- Reject new work during graceful shutdown.
- Do not persist documents or extraction results by default.

## Kubernetes manifests

### Deployment

The planned `Deployment` must:

- Start with one replica.
- Use an immutable image tag or digest, never `latest`.
- expose container port 8080;
- load non-secret settings from `ConfigMap` and provider credentials from `Secret`;
- define startup/readiness/liveness HTTP probes;
- define CPU, memory, and ephemeral-storage requests and limits;
- mount a bounded `emptyDir` at `/tmp` when the root filesystem is read-only;
- use rolling updates with no unbounded surge;
- set a termination grace period compatible with the request timeout;
- include stable app labels and selectors.

Initial resource values are hypotheses until measured. A reasonable starting point is 250m CPU/256 MiB memory requests and 1 CPU/1 GiB memory limits, with enough ephemeral storage for the configured maximum document. Record measured peak memory before presenting these as tuned values.

### Pod security context

Require:

- `runAsNonRoot: true`;
- fixed non-zero user and group IDs;
- `allowPrivilegeEscalation: false`;
- `readOnlyRootFilesystem: true`;
- all Linux capabilities dropped;
- runtime-default seccomp profile.

### Service

- Use a `ClusterIP` Service on port 80 targeting container port 8080.
- Do not expose a public LoadBalancer by default.
- Add Ingress only when a target environment, TLS strategy, body-size limit, and authentication boundary are defined.

### ConfigMap and Secret

`ConfigMap` contains `OPENAI_BASE_URL`, `DDE_MODEL`, `DDE_AUTH_MODE`, limits, render settings, log level, and port. `secret.example.yaml` may contain an `OPENAI_API_KEY` placeholder only and must never contain a real credential. Prefer Microsoft Entra ID with Azure Workload Identity for hosted deployments; use a Kubernetes Secret only when key authentication is unavoidable.

### Probes

- Startup probe: `/healthz`, allowing for application import/start time.
- Readiness probe: `/readyz`, indicating the pod can accept work without making a provider request.
- Liveness probe: `/healthz`; it must detect a stuck process without depending on external provider availability.

### Scaling

The first hosted version is synchronous and stateless, so horizontal replication is possible. Do not ship an HPA until concurrency, latency, provider quotas, and memory usage have been measured. Scaling pods cannot solve provider rate limits.

## Persistence and Amazon RDS

No relational database, including Amazon RDS, is required for the challenge scope. The API returns results directly and uses ephemeral workspace only. If durable jobs, audit history, or multi-tenant accounts are introduced later, persistence must receive a separate product requirement, threat model, retention policy, and architecture decision.

## Network and secret controls

- Allow outbound HTTPS only to the configured OpenAI Responses-compatible endpoint.
- Avoid logging request bodies or secrets.
- Use TLS at the ingress or service-mesh boundary before exposing the API externally.
- Add authentication and rate limiting before public exposure; neither is optional for an internet-facing deployment.
- A NetworkPolicy is recommended when the cluster networking implementation enforces it.

## Kubernetes verification

Static checks:

```bash
kubectl apply --dry-run=client -f deploy/k8s/configmap.yaml
kubectl apply --dry-run=client -f deploy/k8s/deployment.yaml
kubectl apply --dry-run=client -f deploy/k8s/service.yaml
```

Cluster smoke checks when a cluster is available:

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl rollout status deployment/dde
kubectl port-forward service/dde 8080:80
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/readyz
```

Then upload one small fixture and verify the response against its ground truth. Delete any locally created real-secret manifest after the test and ensure it is ignored by Git.

## Hosting acceptance criteria

Docker packaging is complete when:

- the image builds from a clean checkout;
- it runs as non-root;
- CLI extraction and offline validation work with mounted fixtures;
- hosted health endpoints work;
- no credentials are present in image history or tracked files.

Kubernetes packaging is complete when:

- all committed manifests pass client-side dry-run and available schema validation;
- the Deployment becomes ready in a test cluster;
- probes and graceful shutdown behave correctly;
- one forwarded extraction matches fixture expectations;
- security context, resources, immutable image reference, ConfigMap, and Secret wiring are visible in the manifest.

## Known deployment limitations

- The synchronous API ties request duration to document rendering and provider latency.
- The initial service has no durable queue, retries across pod loss, or persisted result retrieval.
- External model availability and quotas remain dependencies.
- Memory use grows with page count and rendering resolution.
- Kubernetes manifests demonstrate a hosting target; they do not establish production readiness, high availability, or cost efficiency.