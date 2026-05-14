# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Download Harpocrate SDK before uv sync (pyproject.toml references vendor/).
# Le nom doit respecter PEP 427 (name-version-pythontag-abitag-platformtag.whl)
# pour que uv accepte le wheel via [tool.uv.sources]. La vraie version vit dans
# les métadonnées internes du wheel ; 0.0.0-py3-none-any est un placeholder
# accepté côté outillage.
ARG HARPOCRATE_URL=https://vault.yoops.org
RUN mkdir -p /app/vendor && \
    curl -fsSL "${HARPOCRATE_URL}/v1/sdk/python-wheel" \
        -o /app/vendor/harpocrate-0.4.0-py3-none-any.whl

# Install Python deps (cacheable layer)
COPY pyproject.toml uv.lock /app/
# Note : `--frozen` est volontairement absent tant que `uv.lock` n'a pas été
# regénéré sur un hôte Linux/WSL avec le wheel Harpocrate présent. uv résout
# les deps à partir de pyproject.toml au build. À ré-activer quand un lock
# autoritaire sera commité (M2 ou plus tard, après bootstrap LXC 303).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# Copy application source
COPY src /app/src
COPY migrations /app/migrations

# Final install with project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "uvicorn", "rag.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
