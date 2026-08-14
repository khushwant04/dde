# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:a5cc441fb52ae405b9080ea1586736ff4e08daa2fbe18b14d4d544f01641db84

FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN python -m pip install uv==0.11.0

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime

ARG VCS_REF=uncommitted
ARG IMAGE_VERSION=unreleased

LABEL org.opencontainers.image.title="Document Data Extractor" \
      org.opencontainers.image.description="Bounded financial-document extraction CLI and API" \
      org.opencontainers.image.source="https://github.com/khushwant04/dde" \
      org.opencontainers.image.version="${IMAGE_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="python:3.12.14-slim-bookworm@sha256:a5cc441fb52ae405b9080ea1586736ff4e08daa2fbe18b14d4d544f01641db84"

ENV HOME=/nonexistent \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp

RUN groupadd --gid 10001 dde \
    && useradd --uid 10001 --gid 10001 --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin dde

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM

CMD ["python", "-m", "dde", "--help"]
