# Deployment Requirements

**Status: Hosted API, secure Docker image, and minimal Kubernetes templates implemented.** The bounded synchronous FastAPI adapter and multi-stage fixed-non-root image are current. The templates pass local structure/policy, `kubectl` client dry-run, and k3s API-server dry-run checks. An isolated k3d v5.9.0/k3s v1.35.5 smoke pulled the pinned image, completed rollout, served both probes through the ClusterIP Service, verified the runtime security/filesystem boundary, rejected an unsupported upload without a provider call, and handled an idle SIGTERM with exit code zero before readiness recovered. No configured-provider extraction, active-request shutdown, NetworkPolicy, vulnerability scan, high-availability, or production smoke was run; this is not a production-readiness claim.

## Deployment objectives

1. Reproduce the CLI environment with Docker.
2. Run the same application service behind a minimal HTTP adapter.
3. Provide a stateless Kubernetes workload template with explicit security and resource boundaries.
4. Inject model configuration and credentials without rebuilding the image.
5. Provide health checks, resource boundaries, and secure runtime defaults.

## Delivery priority

- **Core gate:** native CLI, extraction, validation, fixtures, evaluation, tests, and README.
- **Packaging gate:** Docker image builds and runs the documented CLI sample.
- **Hosting gate:** HTTP adapter and local container smoke test.
- **Kubernetes static gate:** committed templates parse, satisfy repository policy checks, and pass client-side dry-run.
- **Kubernetes cluster gate:** after provider configuration exists, deploy the published image and pass rollout, health, extraction, and graceful-shutdown smokes in an available cluster.

Do not begin Kubernetes work while a core-gate acceptance test is failing.

## Repository paths

```text
Dockerfile
.dockerignore
deploy/
`-- k8s/
    |-- deployment.yaml
    |-- service.yaml
    |-- configmap.yaml
    `-- secret.example.yaml
```

Deployment guidance remains in this owning document rather than a duplicate README below `deploy/`. An optional `ingress.yaml`, `networkpolicy.yaml`, batch `job.yaml`, or Kustomize overlay is stretch work after the minimal manifest set passes.

## Docker requirements

The implemented image uses two stages from the official `python:3.12.14-slim-bookworm` index pinned at `sha256:a5cc441fb52ae405b9080ea1586736ff4e08daa2fbe18b14d4d544f01641db84`. The builder pins `uv==0.11.0` and runs `uv sync --frozen --no-dev`; the runtime receives only the non-editable virtual environment. A deny-by-default `.dockerignore` sends only the Dockerfile, lock/package metadata, license/README, and `src/`. The runtime uses fixed UID/GID `10001:10001`, contains no repository source tree, fixtures, tests, or docs and no `uv`/pytest, and supports CLI or Uvicorn commands. This image was built and exercised on linux/amd64; other architectures and vulnerability-scan status are not claimed.

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

The initial build may require registry/package network access unless an approved local mirror/cache already contains the immutable base and locked artifacts. Runtime verification is explicitly offline:

```bash
docker build --pull \
  --build-arg VCS_REF="$(git rev-parse HEAD)" \
  --build-arg IMAGE_VERSION=unreleased \
  -t dde:local .

SECURITY_FLAGS='--network none --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m --cap-drop ALL --security-opt no-new-privileges'

docker run --rm $SECURITY_FLAGS dde:local python -m dde --help
docker run --rm $SECURITY_FLAGS \
  --mount type=bind,src="$PWD/samples",dst=/work,readonly \
  dde:local python -m dde extract /work/documents/invoice_c.txt \
  --provider fake --fake-response-dir /work/fake_responses

docker image inspect dde:local --format '{{.Config.User}}'
```

The executed gate additionally revalidated the extracted envelope, asserted UID/GID `10001:10001`, proved `/app` unwritable and `/tmp` writable, checked forbidden repository paths and development tools are absent, inspected image environment/history for provider secrets, started Uvicorn with `--network none`, called `/healthz` and `/readyz` over container loopback, and verified SIGTERM exit code zero. These checks establish this local image boundary only; they are not a vulnerability scan, image-signing/SBOM claim, multi-architecture result, or production-readiness claim.

## Hosted API requirements

The implemented `dde.api` adapter:

- listens through an external ASGI command such as `uvicorn dde.api:app --host 0.0.0.0 --port ${PORT:-8080}`;
- stays stateless and saves uploads only in request-scoped temporary storage;
- bounds the complete request before multipart parsing and applies the stricter document-file limit before loading or provider calls;
- serves `/healthz` and `/readyz` without billable model requests;
- applies separate provider and synchronous response deadlines;
- limits concurrent expensive requests per process and rejects excess work without an unbounded queue;
- rejects new work during graceful shutdown;
- does not persist documents or extraction results; and
- returns sanitized transport errors without provider payloads, local paths, credentials, or stack traces.

A `504` response is a client deadline, not proof that a Python thread or remote provider call was cancelled. Timed-out workers keep their concurrency slot and temporary workspace until they finish, then clean up in their own `finally` path. The adapter has no authentication, TLS termination, or distributed rate limiting; those controls are mandatory before internet exposure.

## Kubernetes manifests

The committed minimal set is a deployment template, not evidence of a running environment. `deployment.yaml` pins the published `docker.io/khushwant04/dde:v0.2.0` linux/amd64 image by immutable OCI index digest `sha256:d3a1da7971ae8b6e977b272cf8f92c0b04947418a894c84b5d5854e3feae6e98`. The image was built from release commit `7dffd3dae2a2eaac0391c1c4991fdb7df4db2669` with the matching OCI revision label and a BuildKit provenance attestation; it is not represented as vulnerability-scanned, signed, SBOM-published, or multi-architecture. The template uses API-key authentication only to make the Secret boundary explicit; Azure-hosted environments should instead configure Workload Identity and remove the `OPENAI_API_KEY` reference after testing that identity path.

### Deployment

The committed `Deployment`:

- starts with one replica;
- uses the published immutable Docker Hub digest, never `latest`;
- exposes container port 8080;
- loads non-secret settings from `ConfigMap` and the API key from an explicit `Secret` key reference;
- defines startup/readiness/liveness HTTP probes;
- defines CPU, memory, and ephemeral-storage requests and limits;
- mounts a 256 MiB bounded `emptyDir` at `/tmp` with a read-only root filesystem;
- uses rolling updates with `maxSurge: 1` and `maxUnavailable: 0`;
- gives shutdown 180 seconds, longer than the 130-second API response deadline; provider retries or repair work may still outlive this bound and be terminated by Kubernetes;
- disables service-account-token mounting and service-link environment injection; and
- uses stable app labels and selectors.

The initial 250m CPU/256 MiB memory requests, 1 CPU/1 GiB memory limits, and storage values are unmeasured hypotheses. Record provider-path latency and peak CPU, memory, writable storage, and log use before treating them as tuned capacity values.

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

### Preparing the templates

Before using a cluster:

1. Confirm the pinned published digest supports the target architecture; the current artifact is verified only for linux/amd64.
2. Replace `OPENAI_BASE_URL` and `DDE_MODEL` in `configmap.yaml` with the intended provider values and confirm its data-handling boundary.
3. Prefer Azure Workload Identity where available. If API-key authentication is unavoidable, materialize `deploy/k8s/secret.yaml` locally from `secret.example.yaml`, replace `REPLACE_ME`, restrict file permissions, and never commit it; `.gitignore` excludes that path.
4. Add environment-specific TLS termination, authentication, request-size enforcement, rate limiting, and an enforcing NetworkPolicy before any public exposure. The committed Service is cluster-internal and no Ingress is supplied.
5. Re-measure resources and concurrency under representative documents and provider latency before scaling or adding an HPA.

The example Secret and ConfigMap placeholders can satisfy local readiness configuration checks but cannot perform a real extraction. `/readyz` intentionally checks local lifecycle/configuration only and never calls the provider.

## Kubernetes verification

Static checks (executed with kubectl v1.35.3):

```bash
uv run pytest tests/test_k8s_manifests.py
kubectl apply --dry-run=client -f deploy/k8s/configmap.yaml
kubectl apply --dry-run=client -f deploy/k8s/secret.example.yaml
kubectl apply --dry-run=client -f deploy/k8s/deployment.yaml
kubectl apply --dry-run=client -f deploy/k8s/service.yaml
```

These static checks validate parseable Kubernetes objects and repository security policy; they do not contact a cluster, pull the image, start a pod, or test provider connectivity.

The final v0.2.0-digest isolated smoke used k3d v5.9.0 with k3s v1.35.5. All four objects passed API-server dry-run and applied in a dedicated namespace; the deployment pulled the pinned OCI index digest and became ready, `/healthz` and `/readyz` returned through the ClusterIP Service, UID/GID and read-only-root plus writable-`/tmp` behavior matched the manifest, no Ingress/HPA/public Service existed, and an idle SIGTERM exited zero before Kubernetes restored readiness. The smoke intentionally used unusable provider placeholders, so it proved sanitized `415` upload rejection but not successful extraction or provider connectivity. The temporary cluster was deleted after evidence collection, and the pre-existing global context remained `aks-prod-global-01`.

Configured-provider completion checks:

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

Kubernetes template packaging is statically complete when:

- all committed manifests pass YAML structure/policy tests and client-side dry-run;
- security context, resources, published immutable image reference, ConfigMap, and Secret wiring are visible in the manifest;
- the Service remains `ClusterIP` and no public Ingress, LoadBalancer, or unmeasured HPA is supplied; and
- no real credential or private document is present.

Kubernetes configured-provider readiness remains unverified until:

- the provider values are replaced with real deployment values;
- one forwarded extraction matches fixture expectations; and
- active provider work is exercised during pod termination to measure whether it finishes inside the 180-second grace period.

## Known deployment limitations

- The synchronous API ties request duration to document rendering and provider latency; its response deadline cannot forcibly cancel a running Python worker or remote provider request, so capacity and temporary data remain occupied until that worker exits.
- The initial service has no durable queue, retries across pod loss, or persisted result retrieval.
- External model availability and quotas remain dependencies.
- Memory use grows with page count and rendering resolution.
- Kubernetes manifests demonstrate a hosting target; they do not establish production readiness, high availability, or cost efficiency.