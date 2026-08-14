from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
BASE_REFERENCE = (
    "python:3.12.14-slim-bookworm@"
    "sha256:a5cc441fb52ae405b9080ea1586736ff4e08daa2fbe18b14d4d544f01641db84"
)


def test_dockerfile_uses_immutable_locked_multistage_runtime() -> None:
    content = DOCKERFILE.read_text()
    assert f"ARG PYTHON_IMAGE={BASE_REFERENCE}" in content
    assert content.count("FROM ${PYTHON_IMAGE}") == 2
    assert "python -m pip install uv==0.11.0" in content
    assert "uv sync --frozen --no-dev --no-install-project" in content
    assert "uv sync --frozen --no-dev --no-editable" in content
    assert "COPY --from=builder /app/.venv /app/.venv" in content
    assert "--chown=10001:10001 /app/.venv" not in content
    assert "USER 10001:10001" in content
    assert "STOPSIGNAL SIGTERM" in content
    assert 'CMD ["python", "-m", "dde", "--help"]' in content
    assert "COPY ." not in content


def test_dockerignore_is_deny_by_default_with_minimal_allowlist() -> None:
    lines = {
        line.strip()
        for line in DOCKERIGNORE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "*" in lines
    assert lines == {
        "*",
        "!Dockerfile",
        "!pyproject.toml",
        "!uv.lock",
        "!README.md",
        "!LICENSE",
        "!src/",
        "!src/**",
    }
    for sensitive in (".env", ".venv", ".git", "samples", "tests", "private-documents"):
        assert f"!{sensitive}" not in lines
