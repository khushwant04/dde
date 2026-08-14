from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
K8S = ROOT / "deploy" / "k8s"
PUBLISHED_IMAGE = (
    "docker.io/khushwant04/dde@sha256:"
    "d3a1da7971ae8b6e977b272cf8f92c0b04947418a894c84b5d5854e3feae6e98"
)
EXPECTED_CONFIG = {
    "OPENAI_BASE_URL",
    "DDE_MODEL",
    "DDE_AUTH_MODE",
    "DDE_MAX_FILE_BYTES",
    "DDE_MAX_PAGES",
    "DDE_MAX_IMAGE_PIXELS",
    "DDE_MAX_TABULAR_ROWS",
    "DDE_MAX_TABULAR_COLUMNS",
    "DDE_MAX_CELL_CHARS",
    "DDE_MAX_TABULAR_CHARS",
    "DDE_MAX_SHEETS",
    "DDE_MAX_XLSX_ZIP_ENTRIES",
    "DDE_MAX_XLSX_UNCOMPRESSED_BYTES",
    "DDE_RENDER_DPI",
    "DDE_REQUEST_TIMEOUT_SECONDS",
    "DDE_MAX_REQUEST_BYTES",
    "DDE_MAX_CONCURRENT_REQUESTS",
    "DDE_API_TIMEOUT_SECONDS",
    "DDE_LOG_LEVEL",
    "PORT",
}


def load_manifest(name: str) -> dict[str, Any]:
    documents = list(yaml.safe_load_all((K8S / name).read_text()))
    assert len(documents) == 1
    manifest = documents[0]
    assert isinstance(manifest, dict)
    return manifest


def test_manifests_are_single_documents_with_expected_kinds() -> None:
    expected = {
        "configmap.yaml": ("v1", "ConfigMap"),
        "deployment.yaml": ("apps/v1", "Deployment"),
        "service.yaml": ("v1", "Service"),
        "secret.example.yaml": ("v1", "Secret"),
    }
    assert {path.name for path in K8S.glob("*.yaml")} == set(expected)
    for name, (api_version, kind) in expected.items():
        manifest = load_manifest(name)
        assert manifest["apiVersion"] == api_version
        assert manifest["kind"] == kind
        assert manifest["metadata"]["name"]


def test_configmap_contains_only_complete_non_secret_runtime_configuration() -> None:
    manifest = load_manifest("configmap.yaml")
    data = manifest["data"]
    assert set(data) == EXPECTED_CONFIG
    assert all(isinstance(value, str) and value for value in data.values())
    assert data["PORT"] == "8080"
    assert data["DDE_AUTH_MODE"] == "api_key"
    assert "OPENAI_API_KEY" not in data
    assert not any("SECRET" in key or "PASSWORD" in key or "TOKEN" in key for key in data)


def test_secret_example_contains_only_an_unusable_placeholder() -> None:
    manifest = load_manifest("secret.example.yaml")
    assert manifest["type"] == "Opaque"
    assert manifest["metadata"]["annotations"] == {"dde.dev/example-only": "true"}
    assert "data" not in manifest
    assert manifest["stringData"] == {"OPENAI_API_KEY": "REPLACE_ME"}


def test_deployment_has_published_immutable_image_and_bounded_rollout() -> None:
    manifest = load_manifest("deployment.yaml")
    spec = manifest["spec"]
    assert spec["replicas"] == 1
    assert spec["revisionHistoryLimit"] == 2
    assert spec["strategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
    }
    pod = spec["template"]["spec"]
    container = pod["containers"][0]
    image = container["image"]
    assert image == PUBLISHED_IMAGE
    assert re.fullmatch(r"[^\s:@]+(?:/[^\s:@]+)+@sha256:[0-9a-f]{64}", image)
    assert ":latest" not in image
    assert "Published v0.2.0 image" in manifest["metadata"]["annotations"]["dde.dev/image-note"]


def test_deployment_uses_fixed_non_root_read_only_security_boundary() -> None:
    manifest = load_manifest("deployment.yaml")
    pod = manifest["spec"]["template"]["spec"]
    pod_security = pod["securityContext"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert pod_security["runAsNonRoot"] is True
    assert pod_security["runAsUser"] == 10001
    assert pod_security["runAsGroup"] == 10001
    assert pod_security["fsGroup"] == 10001
    assert pod_security["seccompProfile"] == {"type": "RuntimeDefault"}

    security = pod["containers"][0]["securityContext"]
    assert security == {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "privileged": False,
        "capabilities": {"drop": ["ALL"]},
    }


def test_deployment_wires_config_secret_port_resources_and_tmp() -> None:
    manifest = load_manifest("deployment.yaml")
    pod = manifest["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert container["ports"] == [{"name": "http", "containerPort": 8080, "protocol": "TCP"}]
    assert container["envFrom"] == [{"configMapRef": {"name": "dde-config"}}]
    assert container["env"] == [
        {
            "name": "OPENAI_API_KEY",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "dde-provider",
                    "key": "OPENAI_API_KEY",
                    "optional": False,
                }
            },
        }
    ]
    resources = container["resources"]
    for boundary in ("requests", "limits"):
        assert set(resources[boundary]) == {"cpu", "memory", "ephemeral-storage"}
        assert all(resources[boundary].values())
    assert pod["volumes"] == [{"name": "temporary-workspace", "emptyDir": {"sizeLimit": "256Mi"}}]
    assert container["volumeMounts"] == [{"name": "temporary-workspace", "mountPath": "/tmp"}]


def test_deployment_probes_are_local_and_grace_exceeds_api_deadline() -> None:
    manifest = load_manifest("deployment.yaml")
    pod = manifest["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["terminationGracePeriodSeconds"] > 130
    expected_paths = {
        "startupProbe": "/healthz",
        "readinessProbe": "/readyz",
        "livenessProbe": "/healthz",
    }
    for probe_name, path in expected_paths.items():
        probe = container[probe_name]
        assert probe["httpGet"] == {"path": path, "port": "http", "scheme": "HTTP"}
        assert probe["failureThreshold"] > 0
        assert probe["periodSeconds"] > 0
        assert probe["timeoutSeconds"] > 0


def test_service_is_cluster_internal_and_matches_deployment() -> None:
    deployment = load_manifest("deployment.yaml")
    service = load_manifest("service.yaml")
    service_spec = service["spec"]
    assert service_spec["type"] == "ClusterIP"
    assert service_spec["ports"] == [
        {"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}
    ]
    assert service_spec["selector"] == deployment["spec"]["selector"]["matchLabels"]
    assert service_spec["selector"].items() <= (
        deployment["spec"]["template"]["metadata"]["labels"].items()
    )


def test_minimal_set_has_no_public_exposure_or_autoscaler() -> None:
    manifests = [load_manifest(path.name) for path in K8S.glob("*.yaml")]
    assert not any(
        manifest["kind"] in {"Ingress", "HorizontalPodAutoscaler"} for manifest in manifests
    )
    assert not any(
        isinstance(value, str) and value == "LoadBalancer"
        for manifest in manifests
        for value in _walk_values(manifest)
    )


def _walk_values(value: object) -> list[object]:
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in [child, *_walk_values(child)]]
    if isinstance(value, list):
        return [item for child in value for item in [child, *_walk_values(child)]]
    return []
