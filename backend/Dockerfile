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

# SDK Harpocrate vendoré en source local (v0.6.0), installé éditable via
# [tool.uv.sources]. Copié avant pyproject.toml pour que uv sync trouve le
# chemin référencé. Le précédent download via `${HARPOCRATE_URL}/v1/sdk/python-wheel`
# a été retiré au profit de cette vendorisation source — versionning explicite,
# pas de dépendance réseau au build.
COPY vendor /app/vendor

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
