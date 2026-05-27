# M1 — Fondations + Auth Bearer · Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le squelette backend FastAPI prêt à recevoir les jalons suivants : config Pydantic, logging structlog, pool asyncpg, migrations runner + 4 migrations, SecretResolver complet (env:// + vault://), auth Bearer master key, endpoints `/health` et `/version`, déployable sur LXC 303 via `dev-deploy.sh`.

**Architecture:** Monolithe FastAPI hébergé dans un container `rag-backend`. Le lifespan FastAPI orchestre le boot : logging → pool DB → migrations idempotentes → SecretResolver → (sync worker en M3). Tous les modules métier (`db/`, `secrets/`, `auth/`, `api/`) sont injectables et testables isolément. Les tests d'intégration spawn un Postgres+pgvector éphémère via `testcontainers-python`. TDD strict : test rouge → impl → test vert → commit.

**Tech Stack:** Python 3.12 · uv · FastAPI · uvicorn · asyncpg (pas SQLAlchemy) · pydantic v2 + pydantic-settings · structlog · httpx · bcrypt · pytest + pytest-asyncio + testcontainers · ruff + mypy --strict · Docker multi-stage · SDK Harpocrate (wheel téléchargé depuis `https://vault.yoops.org/v1/sdk/python-wheel`).

**Référence design** : `docs/superpowers/specs/2026-05-14-rag-mvp-implementation-design.md`.

---

## Convention d'exécution

- Toutes les commandes sont à exécuter depuis `E:\srcs\ag-flow.rag\backend/` sauf indication contraire (chemins relatifs au repo root parfois explicités).
- Sur Windows local, utiliser PowerShell pour les commandes ; sur LXC 303, bash.
- Chaque task se termine par un commit en français conventionnel (`feat:`, `test:`, `chore:`…) sur la branche `dev`.
- Aucune livraison sur LXC 303 avant la **Task 18** (smoke deploy final).

---

## Task 1 — Squelette projet uv + ruff + mypy

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/.dockerignore`
- Create: `backend/README.md`
- Create: `backend/vendor/.gitkeep`
- Create: `backend/src/rag/__init__.py`
- Create: `backend/src/rag/api/__init__.py`
- Create: `backend/src/rag/auth/__init__.py`
- Create: `backend/src/rag/db/__init__.py`
- Create: `backend/src/rag/secrets/__init__.py`
- Create: `backend/src/rag/indexer/__init__.py`
- Create: `backend/src/rag/services/__init__.py`
- Create: `backend/src/rag/schemas/__init__.py`
- Create: `backend/src/rag/sync/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/unit/__init__.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/api/__init__.py`
- Modify: `.gitignore` (ajout `backend/.venv/`, `backend/vendor/*.whl`, `backend/uv.lock` non — il doit être commité)

- [ ] **Step 1.1 : Créer `backend/.python-version`**

Contenu :
```
3.12
```

- [ ] **Step 1.2 : Créer `backend/pyproject.toml`**

```toml
[project]
name = "rag"
version = "0.1.0"
description = "ag-flow.rag — service d'infrastructure RAG"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "asyncpg>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "httpx>=0.27",
    "bcrypt>=4.2",
    "python-multipart>=0.0.20",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "testcontainers[postgres]>=4.8",
    "ruff>=0.7",
    "mypy>=1.13",
    "types-bcrypt",
]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rag"]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "ASYNC"]
ignore = ["E501"]  # géré par formatter

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["B011"]  # assert False OK dans les tests

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
warn_redundant_casts = true
files = ["src/rag"]

[[tool.mypy.overrides]]
module = ["asyncpg.*", "testcontainers.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
markers = [
    "smoke: end-to-end tests calling real external services (opt-in)",
]
```

- [ ] **Step 1.3 : Créer `backend/.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
.git/
.env
.env.example
README.md
```

- [ ] **Step 1.4 : Créer `backend/README.md`**

```markdown
# rag — Backend

Service d'infrastructure RAG. Spec : `../docs/superpowers/specs/2026-05-14-rag-mvp-implementation-design.md`.

## Quickstart local (Windows)

```powershell
cd backend
uv sync
./scripts/fetch-harpocrate-sdk.sh   # télécharge le wheel dans vendor/
uv sync                              # ré-install pour prendre le wheel local
uv run pytest -v
```

## Tests

- Unit (rapides, sans réseau) : `uv run pytest tests/unit -v`
- Integration (testcontainers Postgres) : `uv run pytest tests/integration -v`
- API : `uv run pytest tests/api -v`
- Smoke (opt-in, providers réels) : `uv run pytest -m smoke -v`
- Couverture : `uv run pytest --cov=src/rag --cov-report=term-missing`

## Lint, format, type check

```powershell
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src/rag
```
```

- [ ] **Step 1.5 : Créer les `__init__.py` vides**

Pour chacun de ces fichiers, créer un fichier vide :
- `backend/src/rag/__init__.py`
- `backend/src/rag/api/__init__.py`
- `backend/src/rag/auth/__init__.py`
- `backend/src/rag/db/__init__.py`
- `backend/src/rag/secrets/__init__.py`
- `backend/src/rag/indexer/__init__.py`
- `backend/src/rag/services/__init__.py`
- `backend/src/rag/schemas/__init__.py`
- `backend/src/rag/sync/__init__.py`
- `backend/tests/__init__.py`
- `backend/tests/unit/__init__.py`
- `backend/tests/integration/__init__.py`
- `backend/tests/api/__init__.py`

Contenu : aucun (fichier vide).

- [ ] **Step 1.6 : Créer `backend/vendor/.gitkeep`**

Fichier vide. Le dossier `vendor/` contiendra le wheel Harpocrate téléchargé en Task 13.

- [ ] **Step 1.7 : Mettre à jour `.gitignore` (root)**

Ajouter à la fin de `.gitignore` :
```
# Backend
backend/.venv/
backend/vendor/*.whl
backend/.pytest_cache/
backend/.ruff_cache/
backend/.mypy_cache/
backend/__pycache__/
backend/**/__pycache__/
```

`uv.lock` doit rester commité (déterminisme).

- [ ] **Step 1.8 : `uv sync` initial**

Run depuis `backend/` :
```powershell
uv sync
```

Expected : `.venv/` créé, `uv.lock` généré, toutes les deps installées.

- [ ] **Step 1.9 : Smoke ruff + mypy**

Run :
```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/rag
```

Expected : 0 erreur (modules vides, mais infra OK).

- [ ] **Step 1.10 : Commit**

```bash
git add backend/ .gitignore
git commit -m "feat(backend): squelette projet uv + ruff + mypy strict"
```

---

## Task 2 — Logging structlog

**Files:**
- Create: `backend/src/rag/logging_setup.py`
- Create: `backend/tests/unit/test_logging.py`

- [ ] **Step 2.1 : Écrire le test rouge**

Créer `backend/tests/unit/test_logging.py` :

```python
from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
import structlog

from rag.logging_setup import setup_logging


def test_setup_logging_console_dev(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="INFO", environment="dev")
    log = structlog.get_logger("test")
    log.info("hello", workspace="harpocrate")

    captured = capsys.readouterr().out
    assert "hello" in captured
    assert "harpocrate" in captured


def test_setup_logging_json_prod(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="INFO", environment="prod")
    log = structlog.get_logger("test")
    log.info("event", key="value")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == "event"
    assert parsed["key"] == "value"
    assert parsed["level"] == "info"
    assert "timestamp" in parsed


def test_setup_logging_filters_below_level(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="WARNING", environment="prod")
    log = structlog.get_logger("test")
    log.info("should_not_appear")
    log.warning("should_appear")

    output = capsys.readouterr().out
    assert "should_not_appear" not in output
    assert "should_appear" in output


def test_setup_logging_invalid_level_raises() -> None:
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logging(level="NOTALEVEL", environment="dev")
```

- [ ] **Step 2.2 : Lancer le test pour confirmer le rouge**

Run depuis `backend/` :
```powershell
uv run pytest tests/unit/test_logging.py -v
```

Expected : 4 tests FAILED avec `ModuleNotFoundError: No module named 'rag.logging_setup'`.

- [ ] **Step 2.3 : Écrire l'implémentation**

Créer `backend/src/rag/logging_setup.py` :

```python
from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog

Environment = Literal["dev", "staging", "prod"]


def setup_logging(level: str, environment: Environment) -> None:
    """Configure structlog + stdlib logging.

    - `dev`        → console renderer avec couleurs (lisible humain).
    - `staging`/`prod` → JSONRenderer (consommable par Alloy/Loki).
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}")

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment == "dev":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
```

Note : `ConsoleRenderer(colors=False)` en dev pour que `capsys` capture la sortie sans codes ANSI. Le `False` ici n'est qu'une question de testabilité — production garde JSON, dev garde lisible.

- [ ] **Step 2.4 : Lancer les tests, vérifier le vert**

```powershell
uv run pytest tests/unit/test_logging.py -v
```

Expected : 4 tests PASSED.

- [ ] **Step 2.5 : Vérifier ruff + mypy**

```powershell
uv run ruff check src/rag/logging_setup.py tests/unit/test_logging.py
uv run mypy src/rag/logging_setup.py
```

Expected : 0 erreur.

- [ ] **Step 2.6 : Commit**

```bash
git add backend/src/rag/logging_setup.py backend/tests/unit/test_logging.py
git commit -m "feat(logging): structlog JSON prod + console dev"
```

---

## Task 3 — Configuration Pydantic Settings

**Files:**
- Create: `backend/src/rag/config.py`
- Create: `backend/tests/unit/test_config.py`

- [ ] **Step 3.1 : Écrire les tests rouges**

Créer `backend/tests/unit/test_config.py` :

```python
from __future__ import annotations

from pydantic import ValidationError
import pytest

from rag.config import Settings, HarpocrateClientConfig


def test_settings_minimal_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")

    s = Settings()

    assert s.rag_master_key.get_secret_value() == "mk_test_123456"
    assert s.environment == "dev"
    assert s.log_level == "INFO"
    assert s.sync_worker_poll_interval_seconds == 30
    assert "rag" in s.harpocrate_api_keys
    assert s.harpocrate_api_keys["rag"].token.get_secret_value() == "hrpv_1_abc"
    assert str(s.harpocrate_api_keys["rag"].url) == "https://vault.example.com/"


def test_settings_missing_master_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.delenv("RAG_MASTER_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_no_harpocrate_keys_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    for k in list(__import__("os").environ):
        if k.startswith("HARPOCRATE_"):
            monkeypatch.delenv(k, raising=False)

    with pytest.raises(ValidationError, match="No Harpocrate API key configured"):
        Settings()


def test_settings_multiple_harpocrate_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_a")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_PROD", "hrpv_1_b")
    monkeypatch.setenv("HARPOCRATE_API_URL_PROD", "https://vault.example.com")

    s = Settings()

    assert set(s.harpocrate_api_keys.keys()) == {"rag", "prod"}


def test_harpocrate_token_missing_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ORPHAN", "hrpv_1_x")
    monkeypatch.delenv("HARPOCRATE_API_URL_ORPHAN", raising=False)

    with pytest.raises(ValidationError, match="HARPOCRATE_API_URL_ORPHAN"):
        Settings()
```

- [ ] **Step 3.2 : Lancer pour vérifier le rouge**

```powershell
uv run pytest tests/unit/test_config.py -v
```

Expected : tests FAILED (`ModuleNotFoundError: No module named 'rag.config'`).

- [ ] **Step 3.3 : Écrire l'implémentation**

Créer `backend/src/rag/config.py` :

```python
from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarpocrateClientConfig(BaseModel):
    url: AnyHttpUrl
    token: SecretStr


class Settings(BaseSettings):
    """Configuration applicative — lue depuis le .env + env vars.

    Les paires HARPOCRATE_API_TOKEN_<ID> / HARPOCRATE_API_URL_<ID> sont
    consolidées dans `harpocrate_api_keys: dict[str, HarpocrateClientConfig]`
    via un model_validator. Au moins une paire est requise.
    """

    database_url: PostgresDsn
    rag_postgres_admin_url: PostgresDsn
    rag_master_key: SecretStr
    rag_public_url: AnyHttpUrl

    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    sync_worker_poll_interval_seconds: int = 30

    harpocrate_api_keys: dict[str, HarpocrateClientConfig] = {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("rag_master_key")
    @classmethod
    def master_key_non_empty(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("RAG_MASTER_KEY must not be empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def collect_harpocrate_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        keys: dict[str, dict[str, str]] = {}
        for env_key, env_value in os.environ.items():
            upper = env_key.upper()
            if upper.startswith("HARPOCRATE_API_TOKEN_"):
                identifier = upper.removeprefix("HARPOCRATE_API_TOKEN_").lower()
                keys.setdefault(identifier, {})["token"] = env_value
            elif upper.startswith("HARPOCRATE_API_URL_"):
                identifier = upper.removeprefix("HARPOCRATE_API_URL_").lower()
                keys.setdefault(identifier, {})["url"] = env_value

        if not keys:
            raise ValueError(
                "No Harpocrate API key configured — set HARPOCRATE_API_TOKEN_<ID> "
                "and HARPOCRATE_API_URL_<ID> (at least one pair)."
            )

        for identifier, parts in keys.items():
            if "token" not in parts:
                raise ValueError(
                    f"HARPOCRATE_API_TOKEN_{identifier.upper()} declared without "
                    f"matching HARPOCRATE_API_URL_{identifier.upper()}"
                )
            if "url" not in parts:
                raise ValueError(
                    f"HARPOCRATE_API_URL_{identifier.upper()} declared without "
                    f"matching HARPOCRATE_API_TOKEN_{identifier.upper()}"
                )

        data["harpocrate_api_keys"] = {
            identifier: {"url": parts["url"], "token": parts["token"]}
            for identifier, parts in keys.items()
        }
        return data
```

- [ ] **Step 3.4 : Lancer les tests, vérifier vert**

```powershell
uv run pytest tests/unit/test_config.py -v
```

Expected : 5 tests PASSED.

- [ ] **Step 3.5 : ruff + mypy**

```powershell
uv run ruff check src/rag/config.py tests/unit/test_config.py
uv run mypy src/rag/config.py
```

Expected : 0 erreur.

- [ ] **Step 3.6 : Commit**

```bash
git add backend/src/rag/config.py backend/tests/unit/test_config.py
git commit -m "feat(config): Settings Pydantic + agrégation Harpocrate keys"
```

---

## Task 4 — Dockerfile backend + fetch Harpocrate SDK script

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/scripts/fetch-harpocrate-sdk.sh`
- Modify: `docker-compose-dev.yml` (ajout build context backend)

- [ ] **Step 4.1 : Créer `backend/scripts/fetch-harpocrate-sdk.sh`**

```bash
#!/usr/bin/env bash
# Télécharge le wheel du SDK Harpocrate dans backend/vendor/.
# Utilisé en local (avant `uv sync`) et au build Docker.
#
# Usage :
#   ./scripts/fetch-harpocrate-sdk.sh                       # défaut https://vault.yoops.org
#   HARPOCRATE_URL=https://other.host ./scripts/fetch-harpocrate-sdk.sh

set -euo pipefail

HARPOCRATE_URL="${HARPOCRATE_URL:-https://vault.yoops.org}"
VENDOR_DIR="$(cd "$(dirname "$0")/.." && pwd)/vendor"

mkdir -p "$VENDOR_DIR"
rm -f "$VENDOR_DIR"/harpocrate-*.whl

echo "[fetch-harpocrate-sdk] downloading from $HARPOCRATE_URL/v1/sdk/python-wheel"
curl -fsSL "$HARPOCRATE_URL/v1/sdk/python-wheel" -o "$VENDOR_DIR/harpocrate-sdk.whl"

echo "[fetch-harpocrate-sdk] saved to $VENDOR_DIR/harpocrate-sdk.whl"
```

Rendre exécutable :
```bash
chmod +x backend/scripts/fetch-harpocrate-sdk.sh
```

- [ ] **Step 4.2 : Mettre à jour `backend/pyproject.toml` — ajouter le wheel local en source uv**

À la fin de `backend/pyproject.toml`, ajouter :

```toml
[tool.uv.sources]
harpocrate = { path = "vendor/harpocrate-sdk.whl" }
```

Et dans `[project] dependencies`, ajouter `"harpocrate"` à la liste :

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "asyncpg>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "httpx>=0.27",
    "bcrypt>=4.2",
    "python-multipart>=0.0.20",
    "harpocrate",
]
```

Note : `uv sync` échouera tant que le wheel n'est pas téléchargé. C'est intentionnel — fail fast.

- [ ] **Step 4.3 : Créer `backend/Dockerfile`**

```dockerfile
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

# Download Harpocrate SDK before uv sync (pyproject.toml references vendor/)
ARG HARPOCRATE_URL=https://vault.yoops.org
RUN mkdir -p /app/vendor && \
    curl -fsSL "${HARPOCRATE_URL}/v1/sdk/python-wheel" -o /app/vendor/harpocrate-sdk.whl

# Install Python deps (cacheable layer)
COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src /app/src
COPY migrations /app/migrations

# Final install with project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "uvicorn", "rag.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4.4 : Modifier `docker-compose-dev.yml` — ajouter le build context backend**

Remplacer le service `backend` existant dans `docker-compose-dev.yml` (lignes 22-36) par :

```yaml
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    image: rag-backend:latest
    container_name: rag-backend
    restart: unless-stopped
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      postgres: { condition: service_healthy }
    networks: [rag]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      retries: 5
```

(Le reste du compose — postgres, frontend, caddy, pgweb — reste tel quel.)

- [ ] **Step 4.5 : Test : build local du Dockerfile (sur poste avec Docker, sinon skip jusqu'à Task 18)**

Run depuis le repo root :
```bash
docker build -t rag-backend:dev ./backend
```

Expected : build success, image `rag-backend:dev` créée.

> Si le poste local n'a pas accès réseau à vault.yoops.org, ce step échouera. Dans ce cas, le build définitif sera vérifié en Task 18 sur LXC 303. Continuer.

- [ ] **Step 4.6 : Commit**

```bash
git add backend/Dockerfile backend/scripts/fetch-harpocrate-sdk.sh backend/pyproject.toml docker-compose-dev.yml
git commit -m "feat(docker): Dockerfile backend + fetch SDK Harpocrate au build"
```

---

## Task 5 — Conftest pytest + fixture testcontainers Postgres

**Files:**
- Create: `backend/tests/conftest.py`

- [ ] **Step 5.1 : Créer `backend/tests/conftest.py`**

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

if TYPE_CHECKING:
    pass


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def pg_container() -> AsyncIterator[str]:
    """Spawn un Postgres + pgvector éphémère pour toute la session de tests.

    Yield le DSN asyncpg-compatible (postgresql://...).
    """
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="rag",
        password="ragpass",
        dbname="rag_config",
    ) as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        yield dsn


@pytest_asyncio.fixture(scope="session")
async def session_pool(pg_container: str) -> AsyncIterator[asyncpg.Pool]:
    """Un pool partagé pour la session, sur la base `rag_config` du container."""
    pool = await asyncpg.create_pool(pg_container, min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()
```

Note : `event_loop_policy` est requis pour `pytest-asyncio` en mode strict avec scope session. La conftest s'étoffera dans les Tasks suivantes (clean_db, client, mock_resolver…).

- [ ] **Step 5.2 : Smoke test de la fixture**

Créer temporairement `backend/tests/integration/test_smoke_container.py` (sera supprimé après) :

```python
from __future__ import annotations

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_pg_container_has_pgvector(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        assert result == 1

        # pgvector available ?
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        ext = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert ext == "vector"
```

- [ ] **Step 5.3 : Lancer le smoke**

```powershell
uv run pytest tests/integration/test_smoke_container.py -v
```

Expected : PASSED. Le container `pgvector/pgvector:pg16` est pull si nécessaire (peut prendre 1-2 min au premier run).

> Si Docker n'est pas dispo en local, ce test échoue. Skip jusqu'à exécution sur LXC 303 (Docker présent).

- [ ] **Step 5.4 : Supprimer le smoke test temporaire**

```powershell
rm backend/tests/integration/test_smoke_container.py
```

- [ ] **Step 5.5 : Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: fixture testcontainers pgvector/pg16"
```

---

## Task 6 — Migration runner (db/migrations.py)

**Files:**
- Create: `backend/src/rag/db/migrations.py`
- Create: `backend/migrations/000_schema_migrations.sql`
- Create: `backend/tests/integration/test_migrations.py`

- [ ] **Step 6.1 : Créer la migration `000_schema_migrations.sql`**

`backend/migrations/000_schema_migrations.sql` :

```sql
-- Table de suivi des migrations appliquées.
-- Doit exister avant que le runner essaie d'appliquer la première migration métier.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 6.2 : Écrire les tests rouges**

Créer `backend/tests/integration/test_migrations.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import MigrationError, list_applied, run_migrations


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Construit un dossier de migrations factice pour les tests."""
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "000_schema_migrations.sql").write_text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"
    )
    (d / "001_first.sql").write_text("CREATE TABLE first_table (id INT PRIMARY KEY);")
    (d / "002_second.sql").write_text("CREATE TABLE second_table (id INT PRIMARY KEY);")
    return d


@pytest.mark.asyncio
async def test_run_migrations_applies_all(
    session_pool: asyncpg.Pool, migrations_dir: Path
) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE")

    await run_migrations(session_pool, migrations_dir)

    async with session_pool.acquire() as conn:
        applied = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        assert [r["version"] for r in applied] == ["000_schema_migrations", "001_first", "002_second"]

        # Tables réellement créées
        first = await conn.fetchval(
            "SELECT to_regclass('public.first_table')::text"
        )
        assert first == "first_table"


@pytest.mark.asyncio
async def test_run_migrations_idempotent(
    session_pool: asyncpg.Pool, migrations_dir: Path
) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE")

    await run_migrations(session_pool, migrations_dir)
    # Deuxième run : ne doit rien faire
    await run_migrations(session_pool, migrations_dir)

    async with session_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM schema_migrations")
        assert count == 3


@pytest.mark.asyncio
async def test_list_applied(session_pool: asyncpg.Pool, migrations_dir: Path) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE")

    await run_migrations(session_pool, migrations_dir)
    versions = await list_applied(session_pool)
    assert versions == ["000_schema_migrations", "001_first", "002_second"]


@pytest.mark.asyncio
async def test_run_migrations_aborts_on_sql_error(
    session_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "000_schema_migrations.sql").write_text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"
    )
    (d / "001_bad.sql").write_text("SELECT * FROM nonexistent_table;")

    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")

    with pytest.raises(MigrationError, match="001_bad"):
        await run_migrations(session_pool, d)

    # 001_bad NE doit PAS être enregistré comme appliqué
    async with session_pool.acquire() as conn:
        applied = await conn.fetch("SELECT version FROM schema_migrations")
        assert [r["version"] for r in applied] == ["000_schema_migrations"]
```

- [ ] **Step 6.3 : Vérifier le rouge**

```powershell
uv run pytest tests/integration/test_migrations.py -v
```

Expected : ModuleNotFoundError sur `rag.db.migrations`.

- [ ] **Step 6.4 : Implémenter `backend/src/rag/db/migrations.py`**

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class MigrationError(RuntimeError):
    """Une migration SQL a échoué — état de la base : préservé jusqu'à la dernière migration OK."""


async def run_migrations(pool: asyncpg.Pool, migrations_dir: Path) -> None:
    """Applique toutes les migrations `.sql` du dossier non encore appliquées.

    Convention :
    - Fichiers nommés `NNN_description.sql`, triés alphabétiquement.
    - La version stockée dans `schema_migrations.version` est le nom sans `.sql`.
    - La migration `000_schema_migrations.sql` crée la table de suivi elle-même —
      elle est appliquée systématiquement en premier (idempotent).
    - Une migration KO interrompt le runner et lève `MigrationError`.
    """
    files = sorted(p for p in migrations_dir.iterdir() if p.suffix == ".sql")
    if not files:
        log.info("migrations.empty", dir=str(migrations_dir))
        return

    bootstrap = next((f for f in files if f.name.startswith("000_")), None)
    if bootstrap is None:
        raise MigrationError("Missing 000_schema_migrations.sql bootstrap file")

    async with pool.acquire() as conn:
        await conn.execute(bootstrap.read_text(encoding="utf-8"))
        await conn.execute(
            "INSERT INTO schema_migrations (version) VALUES ($1) "
            "ON CONFLICT (version) DO NOTHING",
            bootstrap.stem,
        )

        applied = {
            row["version"]
            for row in await conn.fetch("SELECT version FROM schema_migrations")
        }

        for f in files:
            if f.name.startswith("000_"):
                continue
            version = f.stem
            if version in applied:
                log.debug("migrations.skip", version=version)
                continue

            sql = f.read_text(encoding="utf-8")
            log.info("migrations.apply", version=version)
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
            except asyncpg.PostgresError as e:
                raise MigrationError(f"Migration {version} failed: {e}") from e


async def list_applied(pool: asyncpg.Pool) -> list[str]:
    """Retourne la liste des versions appliquées, triées."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    return [r["version"] for r in rows]
```

- [ ] **Step 6.5 : Vérifier le vert**

```powershell
uv run pytest tests/integration/test_migrations.py -v
```

Expected : 4 tests PASSED.

- [ ] **Step 6.6 : ruff + mypy**

```powershell
uv run ruff check src/rag/db/migrations.py tests/integration/test_migrations.py
uv run mypy src/rag/db/migrations.py
```

- [ ] **Step 6.7 : Commit**

```bash
git add backend/src/rag/db/migrations.py backend/migrations/000_schema_migrations.sql backend/tests/integration/test_migrations.py
git commit -m "feat(db): runner SQL idempotent + table schema_migrations"
```

---

## Task 7 — Migration 001 init (workspaces + indexer_configs)

**Files:**
- Create: `backend/migrations/001_init.sql`
- Create: `backend/tests/integration/test_migration_001.py`

- [ ] **Step 7.1 : Écrire le test rouge**

`backend/tests/integration/test_migration_001.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture(scope="module")
async def applied_pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)
    return session_pool


@pytest.mark.asyncio
async def test_workspaces_table_exists(applied_pool: asyncpg.Pool) -> None:
    async with applied_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_name = 'workspaces' "
            "ORDER BY ordinal_position"
        )
        assert row is not None  # table existe


@pytest.mark.asyncio
async def test_workspaces_columns(applied_pool: asyncpg.Pool) -> None:
    async with applied_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspaces'"
            )
        }
    expected_cols = {
        "id", "name", "api_key_hash", "rag_cnx", "rag_base",
        "sync_interval_seconds", "created_at", "updated_at",
    }
    assert expected_cols.issubset(cols.keys())
    assert cols["sync_interval_seconds"] == "integer"


@pytest.mark.asyncio
async def test_workspaces_name_unique(applied_pool: asyncpg.Pool) -> None:
    async with applied_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('w1', 'h1', 'cnx1', 'base1')"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
                "VALUES ('w1', 'h2', 'cnx2', 'base2')"
            )
        await conn.execute("DELETE FROM workspaces WHERE name = 'w1'")


@pytest.mark.asyncio
async def test_indexer_configs_cascade_on_workspace_delete(
    applied_pool: asyncpg.Pool,
) -> None:
    async with applied_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('w2', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM indexer_configs WHERE workspace_id = $1", ws_id
            )
            == 1
        )

        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM indexer_configs WHERE workspace_id = $1", ws_id
            )
            == 0
        )
```

- [ ] **Step 7.2 : Vérifier le rouge**

```powershell
uv run pytest tests/integration/test_migration_001.py -v
```

Expected : 4 tests FAILED (table `workspaces` n'existe pas).

- [ ] **Step 7.3 : Écrire `backend/migrations/001_init.sql`**

```sql
-- Migration 001 — schémas de base : workspaces + indexer_configs
-- Conforme à specs/01-data-model.md + addition sync_interval_seconds (design 2026-05-14)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE workspaces (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    api_key_hash            TEXT NOT NULL,
    rag_cnx                 TEXT NOT NULL,
    rag_base                TEXT NOT NULL,
    sync_interval_seconds   INT NOT NULL DEFAULT 300,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspaces_name ON workspaces(name);

CREATE TABLE indexer_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    base_url        TEXT,
    api_key_ref     TEXT,
    dimension       INT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id)
);

CREATE INDEX idx_indexer_configs_workspace ON indexer_configs(workspace_id);
```

- [ ] **Step 7.4 : Vérifier le vert**

```powershell
uv run pytest tests/integration/test_migration_001.py -v
```

Expected : 4 tests PASSED.

- [ ] **Step 7.5 : Commit**

```bash
git add backend/migrations/001_init.sql backend/tests/integration/test_migration_001.py
git commit -m "feat(db): migration 001 — workspaces + indexer_configs"
```

---

## Task 8 — Migration 002 workspace_sources

**Files:**
- Create: `backend/migrations/002_workspace_sources.sql`
- Create: `backend/tests/integration/test_migration_002.py`

- [ ] **Step 8.1 : Écrire le test rouge**

```python
# backend/tests/integration/test_migration_002.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspace_sources_table_exists(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspace_sources'"
            )
        }
    expected = {
        "id", "workspace_id", "type", "config",
        "last_indexed_at", "next_sync_at", "created_at",
    }
    assert expected.issubset(cols.keys())
    assert cols["config"] == "jsonb"


@pytest.mark.asyncio
async def test_workspace_sources_default_type_git(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('w_mig002', 'h', 'c', 'b') RETURNING id"
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, config) "
            'VALUES ($1, \'{"url":"https://x"}\') RETURNING id',
            ws_id,
        )
        typ = await conn.fetchval(
            "SELECT type FROM workspace_sources WHERE id = $1", src_id
        )
        assert typ == "git"
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_workspace_sources_next_sync_index(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_sources_next_sync'"
        )
        assert idx == "idx_sources_next_sync"
```

- [ ] **Step 8.2 : Rouge**

```powershell
uv run pytest tests/integration/test_migration_002.py -v
```

- [ ] **Step 8.3 : Écrire `backend/migrations/002_workspace_sources.sql`**

```sql
-- Migration 002 — workspace_sources
-- Conforme à specs/01-data-model.md + addition next_sync_at (design 2026-05-14)

CREATE TABLE workspace_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type            TEXT NOT NULL DEFAULT 'git',
    config          JSONB NOT NULL,
    last_indexed_at TIMESTAMPTZ,
    next_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspace_sources_workspace ON workspace_sources(workspace_id);
CREATE INDEX idx_sources_next_sync ON workspace_sources(next_sync_at)
    WHERE next_sync_at IS NOT NULL;
```

- [ ] **Step 8.4 : Vert**

```powershell
uv run pytest tests/integration/test_migration_002.py -v
```

- [ ] **Step 8.5 : Commit**

```bash
git add backend/migrations/002_workspace_sources.sql backend/tests/integration/test_migration_002.py
git commit -m "feat(db): migration 002 — workspace_sources"
```

---

## Task 9 — Migration 003 jobs (index_jobs + indexed_documents)

**Files:**
- Create: `backend/migrations/003_jobs.sql`
- Create: `backend/tests/integration/test_migration_003.py`

- [ ] **Step 9.1 : Test rouge**

```python
# backend/tests/integration/test_migration_003.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_index_jobs_table(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'index_jobs'"
            )
        }
    expected = {
        "id", "workspace_id", "source_id", "triggered_by", "status",
        "files_changed", "files_skipped", "error_message",
        "started_at", "finished_at", "duration_ms",
    }
    assert expected.issubset(cols)


@pytest.mark.asyncio
async def test_index_jobs_status_default(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('w_mig003', 'h', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by) "
            "VALUES ($1, 'manual') RETURNING id",
            ws_id,
        )
        status = await conn.fetchval(
            "SELECT status FROM index_jobs WHERE id = $1", job_id
        )
        assert status == "pending"
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_indexed_documents_unique_ws_path(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('w_mig003b', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', 'hash1', 'openai/x')",
            ws_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, 'a.md', 'hash2', 'openai/x')",
                ws_id,
            )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_index_jobs_status_index(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_jobs_status_workspace'"
        )
        assert idx == "idx_jobs_status_workspace"
```

- [ ] **Step 9.2 : Rouge**

```powershell
uv run pytest tests/integration/test_migration_003.py -v
```

- [ ] **Step 9.3 : Implémenter `backend/migrations/003_jobs.sql`**

```sql
-- Migration 003 — index_jobs + indexed_documents
-- Conforme à specs/01-data-model.md

CREATE TABLE index_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id       UUID REFERENCES workspace_sources(id) ON DELETE SET NULL,
    triggered_by    TEXT NOT NULL CHECK (triggered_by IN ('webhook', 'manual', 'push', 'schedule')),
    status          TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'done', 'error')),
    files_changed   INT NOT NULL DEFAULT 0,
    files_skipped   INT NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INT
);

CREATE INDEX idx_jobs_status_workspace ON index_jobs(status, workspace_id);
CREATE INDEX idx_jobs_workspace_finished ON index_jobs(workspace_id, finished_at DESC NULLS LAST);

CREATE TABLE indexed_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    indexer_used    TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, path)
);

CREATE INDEX idx_docs_workspace ON indexed_documents(workspace_id);
```

- [ ] **Step 9.4 : Vert**

```powershell
uv run pytest tests/integration/test_migration_003.py -v
```

- [ ] **Step 9.5 : Commit**

```bash
git add backend/migrations/003_jobs.sql backend/tests/integration/test_migration_003.py
git commit -m "feat(db): migration 003 — index_jobs + indexed_documents"
```

---

## Task 10 — Migration 004 oidc_config (vide en M1)

**Files:**
- Create: `backend/migrations/004_oidc.sql`
- Create: `backend/tests/integration/test_migration_004.py`

- [ ] **Step 10.1 : Test rouge**

```python
# backend/tests/integration/test_migration_004.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_oidc_config_table(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'oidc_config'"
            )
        }
    expected = {"id", "issuer", "client_id", "client_secret_ref", "created_at", "updated_at"}
    assert expected.issubset(cols)


@pytest.mark.asyncio
async def test_oidc_config_starts_empty(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM oidc_config")
        assert count == 0
```

- [ ] **Step 10.2 : Rouge**

```powershell
uv run pytest tests/integration/test_migration_004.py -v
```

- [ ] **Step 10.3 : Implémenter `backend/migrations/004_oidc.sql`**

```sql
-- Migration 004 — oidc_config (table créée en M1, peuplée en M5)
-- Conforme à specs/10-auth.md

CREATE TABLE oidc_config (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer              TEXT NOT NULL,
    client_id           TEXT NOT NULL,
    client_secret_ref   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 10.4 : Vert**

```powershell
uv run pytest tests/integration/test_migration_004.py -v
```

- [ ] **Step 10.5 : Commit**

```bash
git add backend/migrations/004_oidc.sql backend/tests/integration/test_migration_004.py
git commit -m "feat(db): migration 004 — oidc_config (table vide en M1)"
```

---

## Task 11 — DB helpers + pool factory

**Files:**
- Create: `backend/src/rag/db/helpers.py`
- Create: `backend/src/rag/db/pool.py`
- Create: `backend/tests/integration/test_pool.py`
- Create: `backend/tests/integration/test_helpers.py`

- [ ] **Step 11.1 : Test rouge pour helpers**

`backend/tests/integration/test_helpers.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.helpers import execute, fetch_all, fetch_one, transaction
from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def migrated(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


@pytest.mark.asyncio
async def test_fetch_one_returns_row(migrated: asyncpg.Pool) -> None:
    await execute(
        migrated,
        "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
        "VALUES ($1, 'h', 'c', 'b')",
        "w_helper",
    )
    row = await fetch_one(
        migrated, "SELECT name FROM workspaces WHERE name = $1", "w_helper"
    )
    assert row is not None
    assert row["name"] == "w_helper"


@pytest.mark.asyncio
async def test_fetch_one_returns_none_when_no_match(migrated: asyncpg.Pool) -> None:
    row = await fetch_one(
        migrated, "SELECT name FROM workspaces WHERE name = $1", "nope"
    )
    assert row is None


@pytest.mark.asyncio
async def test_fetch_all_returns_list(migrated: asyncpg.Pool) -> None:
    await execute(
        migrated,
        "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
        "VALUES ('a', 'h', 'c', 'b'), ('b', 'h', 'c', 'b')",
    )
    rows = await fetch_all(migrated, "SELECT name FROM workspaces ORDER BY name")
    assert [r["name"] for r in rows] == ["a", "b"]


@pytest.mark.asyncio
async def test_transaction_commits(migrated: asyncpg.Pool) -> None:
    async with transaction(migrated) as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('tx_ok', 'h', 'c', 'b')"
        )

    count = await fetch_one(
        migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_ok'"
    )
    assert count is not None and count["c"] == 1


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_error(migrated: asyncpg.Pool) -> None:
    with pytest.raises(RuntimeError, match="forced"):
        async with transaction(migrated) as conn:
            await conn.execute(
                "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
                "VALUES ('tx_rb', 'h', 'c', 'b')"
            )
            raise RuntimeError("forced")

    count = await fetch_one(
        migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_rb'"
    )
    assert count is not None and count["c"] == 0
```

- [ ] **Step 11.2 : Test rouge pour pool factory**

`backend/tests/integration/test_pool.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry


@pytest.mark.asyncio
async def test_registry_caches_workspace_pools(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=4
    )
    await registry.start()

    pool_a1 = await registry.get_workspace_pool("rag_config", pg_container)
    pool_a2 = await registry.get_workspace_pool("rag_config", pg_container)

    assert pool_a1 is pool_a2  # caché

    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_lru_evicts_oldest(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=2
    )
    await registry.start()

    p1 = await registry.get_workspace_pool("rag_config", pg_container)
    p2 = await registry.get_workspace_pool("rag_config", pg_container.replace("/rag_config", "/postgres"))
    p3 = await registry.get_workspace_pool(
        "another", pg_container.replace("/rag_config", "/postgres")
    )

    # p1 doit avoir été fermé (LRU eviction sur max 2)
    assert p1.is_closing() or not p1._initialized
    assert p2 is not None
    assert p3 is not None

    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_config_pool_accessible(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=2
    )
    await registry.start()
    pool = registry.config_pool
    assert isinstance(pool, asyncpg.Pool)
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1")
        assert v == 1
    await registry.close_all()
```

- [ ] **Step 11.3 : Rouge**

```powershell
uv run pytest tests/integration/test_helpers.py tests/integration/test_pool.py -v
```

- [ ] **Step 11.4 : Implémenter `backend/src/rag/db/helpers.py`**

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


async def fetch_one(
    pool: asyncpg.Pool, query: str, *args: Any
) -> asyncpg.Record | None:
    """Exécute la requête et retourne la première ligne (ou None)."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(
    pool: asyncpg.Pool, query: str, *args: Any
) -> list[asyncpg.Record]:
    """Exécute la requête et retourne toutes les lignes."""
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute(pool: asyncpg.Pool, query: str, *args: Any) -> str:
    """Exécute la requête (INSERT/UPDATE/DELETE/DDL), retourne le tag asyncpg."""
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


@asynccontextmanager
async def transaction(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    """Context manager qui ouvre une connexion + une transaction.

    Usage :
        async with transaction(pool) as conn:
            await conn.execute(...)
            await conn.execute(...)

    Rollback automatique si une exception est levée.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
```

- [ ] **Step 11.5 : Implémenter `backend/src/rag/db/pool.py`**

```python
from __future__ import annotations

from collections import OrderedDict

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class WorkspacePoolRegistry:
    """Registry centralisé des pools asyncpg.

    - `config_pool` : pool unique vers la base `rag_config` (toujours actif).
    - `admin_pool` : pool vers la base système `postgres` (utilisé pour CREATE DATABASE).
    - Pools workspaces : créés à la volée, cachés en LRU avec `max_workspace_pools`.
    """

    def __init__(
        self,
        *,
        config_dsn: str,
        admin_dsn: str,
        max_workspace_pools: int = 16,
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        self._config_dsn = config_dsn
        self._admin_dsn = admin_dsn
        self._max_workspace_pools = max_workspace_pools
        self._min_size = min_size
        self._max_size = max_size

        self._config_pool: asyncpg.Pool | None = None
        self._admin_pool: asyncpg.Pool | None = None
        self._workspace_pools: OrderedDict[str, asyncpg.Pool] = OrderedDict()

    async def start(self) -> None:
        """Initialise les pools `config` et `admin`. Idempotent."""
        if self._config_pool is None:
            self._config_pool = await asyncpg.create_pool(
                self._config_dsn, min_size=self._min_size, max_size=self._max_size
            )
            log.info("pool.config.opened", dsn_host=self._config_dsn.split("@")[-1])
        if self._admin_pool is None:
            self._admin_pool = await asyncpg.create_pool(
                self._admin_dsn, min_size=1, max_size=2
            )

    @property
    def config_pool(self) -> asyncpg.Pool:
        if self._config_pool is None:
            raise RuntimeError("WorkspacePoolRegistry.start() not called")
        return self._config_pool

    @property
    def admin_pool(self) -> asyncpg.Pool:
        if self._admin_pool is None:
            raise RuntimeError("WorkspacePoolRegistry.start() not called")
        return self._admin_pool

    async def get_workspace_pool(self, workspace_name: str, dsn: str) -> asyncpg.Pool:
        """Retourne (et crée si besoin) un pool pour la base d'un workspace.

        Cache LRU : si on dépasse `max_workspace_pools`, le moins récemment
        utilisé est fermé.
        """
        if workspace_name in self._workspace_pools:
            self._workspace_pools.move_to_end(workspace_name)
            return self._workspace_pools[workspace_name]

        pool = await asyncpg.create_pool(
            dsn, min_size=self._min_size, max_size=self._max_size
        )
        self._workspace_pools[workspace_name] = pool
        log.info("pool.workspace.opened", workspace=workspace_name)

        # Eviction LRU
        while len(self._workspace_pools) > self._max_workspace_pools:
            oldest_name, oldest_pool = self._workspace_pools.popitem(last=False)
            await oldest_pool.close()
            log.info("pool.workspace.evicted", workspace=oldest_name)

        return pool

    async def close_all(self) -> None:
        for name, pool in list(self._workspace_pools.items()):
            await pool.close()
        self._workspace_pools.clear()

        if self._config_pool is not None:
            await self._config_pool.close()
            self._config_pool = None
        if self._admin_pool is not None:
            await self._admin_pool.close()
            self._admin_pool = None
```

- [ ] **Step 11.6 : Vert**

```powershell
uv run pytest tests/integration/test_helpers.py tests/integration/test_pool.py -v
```

Expected : 8 tests PASSED.

- [ ] **Step 11.7 : Commit**

```bash
git add backend/src/rag/db/helpers.py backend/src/rag/db/pool.py backend/tests/integration/test_helpers.py backend/tests/integration/test_pool.py
git commit -m "feat(db): helpers asyncpg + WorkspacePoolRegistry (LRU)"
```

---

## Task 12 — SecretResolver : parsing + env://

**Files:**
- Create: `backend/src/rag/secrets/resolver.py`
- Create: `backend/tests/unit/test_resolver_parse_env.py`

- [ ] **Step 12.1 : Test rouge**

`backend/tests/unit/test_resolver_parse_env.py` :

```python
from __future__ import annotations

import pytest

from rag.secrets.resolver import (
    EnvVarMissing,
    ParsedRef,
    SecretResolver,
    UnknownAction,
    parse_ref,
)


def test_parse_literal_returns_none() -> None:
    assert parse_ref("sk-literal-value") is None
    assert parse_ref("") is None
    assert parse_ref("plain string") is None


def test_parse_env_ref() -> None:
    ref = parse_ref("${env://OPENAI_API_KEY}")
    assert ref == ParsedRef(action="env", api_key_id=None, path="OPENAI_API_KEY")


def test_parse_vault_ref_root() -> None:
    ref = parse_ref("${vault://api1:anthropic_api_key}")
    assert ref == ParsedRef(action="vault", api_key_id="api1", path="anthropic_api_key")


def test_parse_vault_ref_nested() -> None:
    ref = parse_ref("${vault://prod:shared/databases/postgres_url}")
    assert ref == ParsedRef(
        action="vault", api_key_id="prod", path="shared/databases/postgres_url"
    )


def test_parse_vault_with_email_segment() -> None:
    ref = parse_ref("${vault://api1:alice@example.com/github_token}")
    assert ref == ParsedRef(
        action="vault", api_key_id="api1", path="alice@example.com/github_token"
    )


def test_parse_unknown_action_raises() -> None:
    with pytest.raises(UnknownAction):
        parse_ref("${file:///etc/passwd}")


def test_resolver_returns_literal_unchanged() -> None:
    r = SecretResolver(harpocrate_clients={})
    assert r.resolve("plain-token") == "plain-token"


def test_resolver_resolves_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "value-from-env")
    r = SecretResolver(harpocrate_clients={})
    assert r.resolve("${env://MY_KEY}") == "value-from-env"


def test_resolver_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ABSENT", raising=False)
    r = SecretResolver(harpocrate_clients={})
    with pytest.raises(EnvVarMissing, match="ABSENT"):
        r.resolve("${env://ABSENT}")
```

- [ ] **Step 12.2 : Rouge**

```powershell
uv run pytest tests/unit/test_resolver_parse_env.py -v
```

- [ ] **Step 12.3 : Implémenter `backend/src/rag/secrets/resolver.py` (partie parsing + env)**

```python
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)


class UnknownAction(ValueError):
    """L'action déclarative n'est pas reconnue (`env://`, `vault://`)."""


class EnvVarMissing(KeyError):
    """La variable d'env référencée n'est pas dans `os.environ`."""


class VaultLookupFailed(RuntimeError):
    """Le coffre Harpocrate a refusé ou n'a pas trouvé le secret."""


@dataclass(frozen=True)
class ParsedRef:
    action: str
    api_key_id: str | None
    path: str


# ${env://VAR}
_ENV_RE = re.compile(r"^\$\{env://([^}]+)\}$")
# ${vault://api_id:path}
_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")
# ${anything://...}
_GENERIC_RE = re.compile(r"^\$\{([a-zA-Z][a-zA-Z0-9_-]*)://.*\}$")


def parse_ref(value: str) -> ParsedRef | None:
    """Parse une référence déclarative `${action://...}`.

    Retourne `None` si `value` n'est pas une référence (valeur littérale).
    Lève `UnknownAction` si la chaîne ressemble à une référence mais l'action
    n'est pas supportée.
    """
    if "${" not in value:
        return None

    if m := _ENV_RE.match(value):
        return ParsedRef(action="env", api_key_id=None, path=m.group(1))

    if m := _VAULT_RE.match(value):
        return ParsedRef(action="vault", api_key_id=m.group(1), path=m.group(2))

    if m := _GENERIC_RE.match(value):
        raise UnknownAction(f"Unknown declarative action: {m.group(1)!r}")

    return None


class VaultClient(Protocol):
    """Interface attendue d'un client Harpocrate (pour mocker en tests)."""

    def get_secret(self, path: str) -> str: ...


class SecretResolver:
    """Résolveur de références déclaratives `${env://}` / `${vault://}`.

    - Valeurs littérales : retournées telles quelles.
    - `${env://VAR}` : `os.environ[VAR]` (fail fast si absent).
    - `${vault://id:path}` : appel au `VaultClient` correspondant.
    """

    def __init__(self, harpocrate_clients: dict[str, VaultClient]) -> None:
        self._clients = harpocrate_clients

    def resolve(self, value: str) -> str:
        ref = parse_ref(value)
        if ref is None:
            return value

        if ref.action == "env":
            try:
                return os.environ[ref.path]
            except KeyError as e:
                raise EnvVarMissing(f"Environment variable not set: {ref.path}") from e

        if ref.action == "vault":
            return self._vault_lookup(ref.api_key_id, ref.path)

        raise UnknownAction(f"Unhandled action: {ref.action}")

    def _vault_lookup(self, api_key_id: str | None, path: str) -> str:
        if api_key_id is None:
            raise UnknownAction("vault:// requires an api_key_id")
        if api_key_id not in self._clients:
            raise VaultLookupFailed(
                f"No Harpocrate client configured for api_key_id={api_key_id!r}"
            )
        return self._clients[api_key_id].get_secret(path)
```

- [ ] **Step 12.4 : Vert**

```powershell
uv run pytest tests/unit/test_resolver_parse_env.py -v
```

Expected : 9 tests PASSED.

- [ ] **Step 12.5 : Commit**

```bash
git add backend/src/rag/secrets/resolver.py backend/tests/unit/test_resolver_parse_env.py
git commit -m "feat(secrets): SecretResolver parsing + ${env://} resolution"
```

---

## Task 13 — SecretResolver : vault:// + Harpocrate wrapping

**Files:**
- Create: `backend/src/rag/secrets/vault.py`
- Create: `backend/tests/unit/test_resolver_vault.py`

- [ ] **Step 13.1 : Test rouge**

`backend/tests/unit/test_resolver_vault.py` :

```python
from __future__ import annotations

import pytest

from rag.secrets.resolver import SecretResolver, VaultClient, VaultLookupFailed
from rag.secrets.vault import HarpocrateVaultClient


class FakeVaultClient:
    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = secrets
        self.calls: list[str] = []

    def get_secret(self, path: str) -> str:
        self.calls.append(path)
        if path not in self._secrets:
            raise KeyError(f"secret not found: {path}")
        return self._secrets[path]


def test_resolver_uses_correct_vault_client() -> None:
    api1 = FakeVaultClient({"shared/openai": "sk-real-from-api1"})
    api2 = FakeVaultClient({"shared/openai": "sk-real-from-api2"})

    r = SecretResolver(harpocrate_clients={"api1": api1, "api2": api2})

    assert r.resolve("${vault://api1:shared/openai}") == "sk-real-from-api1"
    assert r.resolve("${vault://api2:shared/openai}") == "sk-real-from-api2"
    assert api1.calls == ["shared/openai"]
    assert api2.calls == ["shared/openai"]


def test_resolver_unknown_api_key_id() -> None:
    r = SecretResolver(harpocrate_clients={"api1": FakeVaultClient({})})
    with pytest.raises(VaultLookupFailed, match="unknown"):
        r.resolve("${vault://unknown:foo}")


def test_harpocrate_client_implements_protocol() -> None:
    # Smoke : la classe satisfait le protocole VaultClient
    assert hasattr(HarpocrateVaultClient, "get_secret")
    # On ne l'instancie pas ici (réseau requis), juste structural.
    client_type: type[VaultClient] = HarpocrateVaultClient
    assert client_type is HarpocrateVaultClient
```

- [ ] **Step 13.2 : Rouge**

```powershell
uv run pytest tests/unit/test_resolver_vault.py -v
```

Expected : ModuleNotFoundError `rag.secrets.vault`.

- [ ] **Step 13.3 : Implémenter `backend/src/rag/secrets/vault.py`**

```python
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class HarpocrateVaultClient:
    """Wrapper minimal autour du SDK officiel Harpocrate.

    Le SDK (`harpocrate.VaultClient`) gère l'extraction du dkey depuis le token
    et le déchiffrement local AES-GCM. On expose une interface `get_secret(path)`
    conforme au protocole `VaultClient` consommé par `SecretResolver`.

    Note : si le wheel `vendor/harpocrate-sdk.whl` n'est pas téléchargé,
    l'import lèvera `ImportError` au démarrage. C'est volontaire — fail fast.
    """

    def __init__(self, url: str, token: str) -> None:
        from harpocrate import VaultClient as _SdkClient  # type: ignore[import-not-found]

        self._url = url
        self._sdk = _SdkClient(url=url, token=token)

    def get_secret(self, path: str) -> str:
        log.debug("vault.lookup", url=self._url, path=path)
        return self._sdk.get_secret(path)
```

- [ ] **Step 13.4 : Vert**

```powershell
uv run pytest tests/unit/test_resolver_vault.py -v
```

Expected : 3 tests PASSED. (Le test sur `HarpocrateVaultClient` ne l'instancie pas — il vérifie juste la classe.)

- [ ] **Step 13.5 : Commit**

```bash
git add backend/src/rag/secrets/vault.py backend/tests/unit/test_resolver_vault.py
git commit -m "feat(secrets): HarpocrateVaultClient wrapping SDK officiel"
```

---

## Task 14 — SecretResolver : cache RAM + invalidation 401

**Files:**
- Modify: `backend/src/rag/secrets/resolver.py`
- Create: `backend/tests/unit/test_resolver_cache.py`

- [ ] **Step 14.1 : Test rouge**

`backend/tests/unit/test_resolver_cache.py` :

```python
from __future__ import annotations

import time

import pytest

from rag.secrets.resolver import SecretResolver, VaultLookupFailed


class CountingFakeClient:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0
        self.fail_until_invalidate = False

    def get_secret(self, path: str) -> str:
        self.calls += 1
        if self.fail_until_invalidate:
            raise PermissionError("401")
        return self.value


def test_cache_hit_avoids_second_lookup() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=60)

    assert r.resolve("${vault://api1:k}") == "v"
    assert r.resolve("${vault://api1:k}") == "v"
    assert client.calls == 1


def test_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=10)

    now = [time.monotonic()]
    monkeypatch.setattr("rag.secrets.resolver.time.monotonic", lambda: now[0])

    r.resolve("${vault://api1:k}")
    now[0] += 5
    r.resolve("${vault://api1:k}")
    assert client.calls == 1

    now[0] += 6  # total 11 > ttl 10
    r.resolve("${vault://api1:k}")
    assert client.calls == 2


def test_invalidate_clears_specific_ref() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)

    r.resolve("${vault://api1:k}")
    r.invalidate("${vault://api1:k}")
    r.resolve("${vault://api1:k}")
    assert client.calls == 2


def test_invalidate_unknown_ref_is_silent() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)
    r.invalidate("${vault://api1:not_cached}")  # ne lève rien


def test_resolve_with_401_retry_invalidates_and_retries() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)

    r.resolve("${vault://api1:k}")  # cached
    assert client.calls == 1

    # Simule un 401 sur le prochain lookup en forçant un nouvel appel via invalidation
    client.fail_until_invalidate = True
    with pytest.raises(VaultLookupFailed):
        r.resolve_with_retry("${vault://api1:k}")

    # Après échec, le 2e essai déclenche un nouveau lookup
    assert client.calls >= 2
```

- [ ] **Step 14.2 : Rouge**

```powershell
uv run pytest tests/unit/test_resolver_cache.py -v
```

- [ ] **Step 14.3 : Étendre `backend/src/rag/secrets/resolver.py`**

Remplacer le contenu de `backend/src/rag/secrets/resolver.py` par :

```python
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)


class UnknownAction(ValueError):
    pass


class EnvVarMissing(KeyError):
    pass


class VaultLookupFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedRef:
    action: str
    api_key_id: str | None
    path: str


_ENV_RE = re.compile(r"^\$\{env://([^}]+)\}$")
_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")
_GENERIC_RE = re.compile(r"^\$\{([a-zA-Z][a-zA-Z0-9_-]*)://.*\}$")


def parse_ref(value: str) -> ParsedRef | None:
    if "${" not in value:
        return None
    if m := _ENV_RE.match(value):
        return ParsedRef(action="env", api_key_id=None, path=m.group(1))
    if m := _VAULT_RE.match(value):
        return ParsedRef(action="vault", api_key_id=m.group(1), path=m.group(2))
    if m := _GENERIC_RE.match(value):
        raise UnknownAction(f"Unknown declarative action: {m.group(1)!r}")
    return None


class VaultClient(Protocol):
    def get_secret(self, path: str) -> str: ...


@dataclass
class _CacheEntry:
    value: str
    expires_at: float


class SecretResolver:
    """Résolveur de références déclaratives avec cache RAM TTL et invalidation.

    - `cache_ttl=0` → pas de cache (utile pour tests).
    - `cache_ttl>0` → cache les résolutions `${vault://}` (jamais les `${env://}`).
    - `invalidate(ref)` → supprime l'entrée cachée pour `ref`.
    - `resolve_with_retry(ref)` → invalide + retry une fois sur 401/PermissionError.
    """

    def __init__(
        self,
        harpocrate_clients: dict[str, VaultClient],
        *,
        cache_ttl: int = 300,
    ) -> None:
        self._clients = harpocrate_clients
        self._cache_ttl = cache_ttl
        self._cache: dict[str, _CacheEntry] = {}

    def resolve(self, value: str) -> str:
        ref = parse_ref(value)
        if ref is None:
            return value

        if ref.action == "env":
            try:
                return os.environ[ref.path]
            except KeyError as e:
                raise EnvVarMissing(f"Environment variable not set: {ref.path}") from e

        if ref.action == "vault":
            return self._vault_lookup_cached(value, ref.api_key_id, ref.path)

        raise UnknownAction(f"Unhandled action: {ref.action}")

    def resolve_with_retry(self, value: str) -> str:
        """Comme `resolve`, mais invalide le cache et retente une fois sur 401."""
        try:
            return self.resolve(value)
        except (PermissionError, VaultLookupFailed) as e:
            log.warning("vault.retry_after_401", ref=value, error=str(e))
            self.invalidate(value)
            try:
                return self.resolve(value)
            except (PermissionError, KeyError) as e2:
                raise VaultLookupFailed(f"Retry after 401 failed for {value!r}") from e2

    def invalidate(self, value: str) -> None:
        self._cache.pop(value, None)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _vault_lookup_cached(
        self, raw_ref: str, api_key_id: str | None, path: str
    ) -> str:
        now = time.monotonic()
        if self._cache_ttl > 0:
            entry = self._cache.get(raw_ref)
            if entry is not None and entry.expires_at > now:
                return entry.value

        if api_key_id is None:
            raise UnknownAction("vault:// requires an api_key_id")
        client = self._clients.get(api_key_id)
        if client is None:
            raise VaultLookupFailed(
                f"No Harpocrate client configured for unknown api_key_id={api_key_id!r}"
            )

        try:
            value = client.get_secret(path)
        except PermissionError as e:
            raise VaultLookupFailed(f"401 on {raw_ref!r}") from e

        if self._cache_ttl > 0:
            self._cache[raw_ref] = _CacheEntry(
                value=value, expires_at=now + self._cache_ttl
            )
        return value
```

- [ ] **Step 14.4 : Vert**

```powershell
uv run pytest tests/unit/test_resolver_cache.py tests/unit/test_resolver_parse_env.py tests/unit/test_resolver_vault.py -v
```

Expected : tous PASSED.

- [ ] **Step 14.5 : Commit**

```bash
git add backend/src/rag/secrets/resolver.py backend/tests/unit/test_resolver_cache.py
git commit -m "feat(secrets): cache RAM TTL + invalidation + resolve_with_retry"
```

---

## Task 15 — Auth Bearer middleware (master key)

**Files:**
- Create: `backend/src/rag/auth/bearer.py`
- Create: `backend/tests/api/test_auth.py`

- [ ] **Step 15.1 : Test rouge**

`backend/tests/api/test_auth.py` :

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from rag.auth.bearer import require_master_key


def build_app(master_key: str) -> FastAPI:
    app = FastAPI()
    app.state.master_key = master_key

    router = APIRouter()

    @router.get("/admin/ping", dependencies=[Depends(require_master_key)])
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(router)
    return app


def test_admin_endpoint_requires_authorization() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_admin_endpoint_rejects_bad_token() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_master_key"


def test_admin_endpoint_accepts_master_key() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Bearer mk_test"})
    assert r.status_code == 200
    assert r.json() == {"ok": "yes"}


def test_authorization_scheme_must_be_bearer() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Basic mk_test"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_auth_scheme"
```

- [ ] **Step 15.2 : Rouge**

```powershell
uv run pytest tests/api/test_auth.py -v
```

- [ ] **Step 15.3 : Implémenter `backend/src/rag/auth/bearer.py`**

```python
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def require_master_key(request: Request) -> None:
    """Dependency FastAPI : valide `Authorization: Bearer <RAG_MASTER_KEY>`.

    Lit la master_key depuis `request.app.state.master_key` (injecté au lifespan).

    Réponses :
    - 401 `missing_bearer_token` si pas d'header.
    - 401 `invalid_auth_scheme` si header présent mais pas `Bearer`.
    - 401 `invalid_master_key` si token ne correspond pas.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
        )

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_auth_scheme",
        )

    provided = parts[1].strip()
    expected = request.app.state.master_key
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_master_key",
        )
```

`hmac.compare_digest` évite les timing attacks sur la comparaison.

- [ ] **Step 15.4 : Vert**

```powershell
uv run pytest tests/api/test_auth.py -v
```

Expected : 4 tests PASSED.

- [ ] **Step 15.5 : Commit**

```bash
git add backend/src/rag/auth/bearer.py backend/tests/api/test_auth.py
git commit -m "feat(auth): require_master_key (Bearer, timing-safe compare)"
```

---

## Task 16 — API health + version

**Files:**
- Create: `backend/src/rag/api/health.py`
- Create: `backend/tests/api/test_health.py`

- [ ] **Step 16.1 : Test rouge**

`backend/tests/api/test_health.py` :

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.health import build_health_router


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.state.environment = "dev"
    app.state.version = "0.1.0"
    app.state.git_sha = "abc1234"
    app.include_router(build_health_router())
    return app


def test_health_returns_ok() -> None:
    client = TestClient(build_test_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_is_public() -> None:
    # Pas d'header Authorization — ça doit marcher
    client = TestClient(build_test_app())
    r = client.get("/health")
    assert r.status_code == 200


def test_version_endpoint() -> None:
    client = TestClient(build_test_app())
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["git"] == "abc1234"
    assert body["environment"] == "dev"
```

- [ ] **Step 16.2 : Rouge**

```powershell
uv run pytest tests/api/test_health.py -v
```

- [ ] **Step 16.3 : Implémenter `backend/src/rag/api/health.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request


def build_health_router() -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/version")
    def version(request: Request) -> dict[str, str]:
        return {
            "version": request.app.state.version,
            "git": request.app.state.git_sha,
            "environment": request.app.state.environment,
        }

    return router
```

- [ ] **Step 16.4 : Vert**

```powershell
uv run pytest tests/api/test_health.py -v
```

Expected : 3 tests PASSED.

- [ ] **Step 16.5 : Commit**

```bash
git add backend/src/rag/api/health.py backend/tests/api/test_health.py
git commit -m "feat(api): endpoints /health (public) et /version"
```

---

## Task 17 — main.py + lifespan

**Files:**
- Create: `backend/src/rag/main.py`
- Create: `backend/tests/api/test_main.py`

- [ ] **Step 17.1 : Test rouge**

`backend/tests/api/test_main.py` :

```python
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import SecretResolver


@pytest_asyncio.fixture
async def test_app_client(pg_container: str) -> AsyncIterator[TestClient]:
    os.environ.setdefault("DATABASE_URL", pg_container)
    os.environ.setdefault("RAG_POSTGRES_ADMIN_URL", pg_container)
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_xyz")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")

    app = build_app(
        version="0.1.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: SecretResolver(harpocrate_clients={}),
        migrations_dir=Path(__file__).resolve().parents[2] / "migrations",
    )

    with TestClient(app) as client:
        yield client


def test_app_boots_and_health_responds(test_app_client: TestClient) -> None:
    r = test_app_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_app_version_response(test_app_client: TestClient) -> None:
    r = test_app_client.get("/version")
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["git"] == "testsha"


def test_admin_route_protected(test_app_client: TestClient) -> None:
    # Pas encore d'endpoint /api/admin/* en M1, mais on peut tester
    # que l'auth est cablée via un endpoint factice qu'on enregistre dans build_app.
    # Si build_app n'en pose pas, on peut l'omettre — ce test sera élargi en M2.
    r = test_app_client.get("/api/admin/ping")
    # 404 acceptable en M1 (pas de route admin encore), 401 acceptable plus tard
    assert r.status_code in (401, 404)
```

- [ ] **Step 17.2 : Rouge**

```powershell
uv run pytest tests/api/test_main.py -v
```

- [ ] **Step 17.3 : Implémenter `backend/src/rag/main.py`**

```python
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI

from rag.api.health import build_health_router
from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.logging_setup import setup_logging
from rag.secrets.resolver import SecretResolver
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)

ResolverFactory = Callable[[Settings], SecretResolver]


def _default_resolver_factory(settings: Settings) -> SecretResolver:
    clients = {
        identifier: HarpocrateVaultClient(
            url=str(cfg.url), token=cfg.token.get_secret_value()
        )
        for identifier, cfg in settings.harpocrate_api_keys.items()
    }
    return SecretResolver(harpocrate_clients=clients)


def _default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


def build_app(
    *,
    version: str = "0.1.0",
    git_sha: str | None = None,
    resolver_factory: ResolverFactory = _default_resolver_factory,
    migrations_dir: Path | None = None,
) -> FastAPI:
    """Factory FastAPI — paramètres injectables pour les tests."""
    settings = Settings()
    setup_logging(settings.log_level, settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("app.lifespan.start", environment=settings.environment)

        app.state.master_key = settings.rag_master_key.get_secret_value()
        app.state.version = version
        app.state.git_sha = git_sha or os.environ.get("GIT_SHA", "unknown")
        app.state.environment = settings.environment

        registry = WorkspacePoolRegistry(
            config_dsn=str(settings.database_url),
            admin_dsn=str(settings.rag_postgres_admin_url),
        )
        await registry.start()
        app.state.pools = registry

        target_dir = migrations_dir or _default_migrations_dir()
        await run_migrations(registry.config_pool, target_dir)

        app.state.resolver = resolver_factory(settings)

        log.info("app.lifespan.ready")
        try:
            yield
        finally:
            log.info("app.lifespan.shutdown")
            await registry.close_all()

    app = FastAPI(
        title="ag-flow.rag",
        version=version,
        lifespan=lifespan,
    )
    app.include_router(build_health_router())
    return app


# Pour `uv run uvicorn rag.main:app`
app = build_app()
```

- [ ] **Step 17.4 : Vert**

```powershell
uv run pytest tests/api/test_main.py -v
```

Expected : 3 tests PASSED. Le boot exécute migrations sur le testcontainer Postgres + sert `/health` et `/version`.

- [ ] **Step 17.5 : Smoke local (optionnel sur Windows) : lancer le serveur**

```powershell
# Pré-requis : .env local avec POSTGRES_* (peut pointer sur LXC 303 :5432), RAG_MASTER_KEY,
# HARPOCRATE_API_TOKEN_RAG, etc. Si pas dispo localement, skip.
uv run uvicorn rag.main:app --reload --port 8000
# Dans un autre terminal :
# curl http://localhost:8000/health  → {"status":"ok"}
```

- [ ] **Step 17.6 : ruff + mypy global**

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/rag
```

Expected : 0 erreur.

- [ ] **Step 17.7 : Commit**

```bash
git add backend/src/rag/main.py backend/tests/api/test_main.py
git commit -m "feat(app): main.py + lifespan FastAPI (migrations au boot, pools, resolver)"
```

---

## Task 18 — Caddyfile minimal + nettoyage `.env.example` + smoke deploy LXC 303

**Files:**
- Create: `Caddyfile` (repo root)
- Modify: `.env.example` (nettoyer aux vars M1 strictement nécessaires)
- Modify: `Install-dev.md` (mettre à jour le snippet `.env` à la création)

- [ ] **Step 18.1 : Créer `Caddyfile` à la racine du repo**

```caddyfile
# Caddyfile dev — reverse proxy HTTP minimal pour LXC 303.
# /api/* → backend:8000 (FastAPI)
# /ui*   → frontend:80 (placeholder, retournera 404 jusqu'à M5)
# /      → backend:8000 health pour debug (à remplacer par redirect /ui en M5)
#
# Pas de TLS — Cloudflare Tunnel gère le HTTPS en front en prod.

{
    auto_https off
}

:80 {
    handle /api/* {
        reverse_proxy backend:8000
    }

    handle /health {
        reverse_proxy backend:8000
    }

    handle /version {
        reverse_proxy backend:8000
    }

    handle /ui* {
        respond "UI not yet deployed (M5)" 404
    }

    handle {
        respond "ag-flow.rag — see /health or /api/*" 200
    }
}
```

- [ ] **Step 18.2 : Nettoyer `.env.example`**

Remplacer `.env.example` par :

```env
# Configuration ag-flow.rag — dev/test (M1)
# Spec : docs/superpowers/specs/2026-05-14-rag-mvp-implementation-design.md

# ─── PostgreSQL (base rag_config) ───────────────────────────
POSTGRES_USER=rag
POSTGRES_PASSWORD=
POSTGRES_DB=rag_config
DATABASE_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/postgres

# ─── Master key API (Bearer admin) ──────────────────────────
RAG_MASTER_KEY=

# ─── URL publique ───────────────────────────────────────────
RAG_PUBLIC_URL=http://192.168.10.184

# ─── Harpocrate (résolution secrets ${vault://...}) ────────
# Au moins une paire HARPOCRATE_API_TOKEN_<ID> / HARPOCRATE_API_URL_<ID> requise.
HARPOCRATE_API_TOKEN_RAG=
HARPOCRATE_API_URL_RAG=https://vault.yoops.org

# ─── Divers ─────────────────────────────────────────────────
ENVIRONMENT=dev
LOG_LEVEL=INFO
SYNC_WORKER_POLL_INTERVAL_SECONDS=30
```

- [ ] **Step 18.3 : Mettre à jour `Install-dev.md`**

Remplacer le bloc `env` "Si .env.example n'existe pas encore (premier setup avant le code backend)" (lignes 68-99) par le contenu identique à `.env.example` ci-dessus, et retirer les sections HMAC / admin local / Listmonk / Keycloak (qui n'existent plus en M1).

Localiser la section "Étape 3 — Configurer le fichier `.env`" et remplacer le code block du snippet `.env` à la création par :

```env
POSTGRES_USER=rag
POSTGRES_PASSWORD=<générer : openssl rand -base64 32 | tr -d '/+=' | head -c 32>
POSTGRES_DB=rag_config
DATABASE_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/postgres
RAG_MASTER_KEY=<générer : openssl rand -base64 48 | tr '+/' '-_' | tr -d '=' | head -c 48>
RAG_PUBLIC_URL=http://192.168.10.184
HARPOCRATE_API_TOKEN_RAG=
HARPOCRATE_API_URL_RAG=https://vault.yoops.org
ENVIRONMENT=dev
LOG_LEVEL=INFO
SYNC_WORKER_POLL_INTERVAL_SECONDS=30
```

Et adapter la liste "Variables critiques à renseigner" pour retirer `KEYCLOAK_CLIENT_SECRET_REF`.

- [ ] **Step 18.4 : Push sur dev**

```bash
git add Caddyfile .env.example Install-dev.md
git commit -m "feat(infra): Caddyfile minimal + .env.example aligne M1"
git push origin dev
```

- [ ] **Step 18.5 : Deploy LXC 303**

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Le script `dev-deploy.sh` va :
1. `git pull origin dev`
2. Build `rag-backend:latest` (Dockerfile télécharge le SDK Harpocrate au build)
3. `docker compose -f docker-compose-dev.yml down/up`

Expected : tous les services `healthy`.

- [ ] **Step 18.6 : Vérifier le déploiement**

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose-dev.yml ps'"
```

Expected : `rag-postgres` healthy, `rag-backend` healthy, `rag-caddy` running.

```bash
ssh pve "pct exec 303 -- curl -s http://localhost:8000/health"
# → {"status":"ok"}
ssh pve "pct exec 303 -- curl -s http://localhost/health"
# → {"status":"ok"}  (via Caddy)
ssh pve "pct exec 303 -- curl -s http://localhost:8000/version"
# → {"version":"0.1.0","git":"...","environment":"dev"}
```

Auth check :
```bash
ssh pve "pct exec 303 -- curl -i http://localhost:8000/api/admin/ping"
# → 404 attendu en M1 (pas d'endpoint admin encore — l'auth sera vérifiée en M2)
```

- [ ] **Step 18.7 : Vérifier les logs**

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose-dev.yml logs --tail=50 backend'"
```

Expected : logs structlog JSON, lignes `app.lifespan.start`, `migrations.apply` pour 001/002/003/004, `app.lifespan.ready`. **Aucune valeur de secret en clair.**

- [ ] **Step 18.8 : Vérifier l'état pgvector**

```bash
ssh pve "pct exec 303 -- bash -c 'docker exec rag-postgres psql -U rag -d rag_config -c \"\\dt\"'"
```

Expected : tables `schema_migrations`, `workspaces`, `indexer_configs`, `workspace_sources`, `index_jobs`, `indexed_documents`, `oidc_config`.

- [ ] **Step 18.9 : Quality gate final**

Depuis le poste local :
```powershell
cd backend
uv run pytest -v --cov=src/rag --cov-report=term-missing
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/rag
```

Expected :
- pytest : tous tests verts
- couverture : ≥ 90% lignes globalement, ≥ 95% sur `secrets/`, `auth/`, `api/health.py`
- ruff : 0 erreur
- mypy : 0 erreur

- [ ] **Step 18.10 : Commit final M1**

Si modifications du quality gate (corrections) :
```bash
git add backend/
git commit -m "chore: quality gate M1 (lint, format, types, coverage)"
git push origin dev
```

Sinon, créer un tag `m1-done` :
```bash
git tag m1-done
git push origin m1-done
```

---

## Récapitulatif M1

À la fin du jalon, le repo contient :

```
backend/
├── pyproject.toml + uv.lock
├── Dockerfile (multi-stage, fetch SDK Harpocrate au build)
├── README.md
├── scripts/fetch-harpocrate-sdk.sh
├── vendor/.gitkeep
├── migrations/
│   ├── 000_schema_migrations.sql
│   ├── 001_init.sql
│   ├── 002_workspace_sources.sql
│   ├── 003_jobs.sql
│   └── 004_oidc.sql
├── src/rag/
│   ├── main.py + lifespan complet
│   ├── config.py (Settings + agrégation Harpocrate keys)
│   ├── logging_setup.py
│   ├── api/health.py (/health, /version)
│   ├── auth/bearer.py (require_master_key)
│   ├── db/{pool.py, helpers.py, migrations.py}
│   ├── secrets/{resolver.py, vault.py}
│   └── (indexer/, services/, schemas/, sync/) — vides, créés en M2-M3
└── tests/
    ├── conftest.py (fixture pg_container, session_pool)
    ├── unit/{test_logging, test_config, test_resolver_parse_env, test_resolver_vault, test_resolver_cache}
    ├── integration/{test_migrations, test_migration_00{1,2,3,4}, test_helpers, test_pool}
    └── api/{test_health, test_auth, test_main}

Caddyfile (root, /api/* → backend, /ui* → 404)
.env.example aligné M1
Install-dev.md à jour
```

Sur LXC 303 :
- Stack docker compose up, tous services healthy.
- `curl http://192.168.10.184/health` → `{"status":"ok"}`.
- `curl http://192.168.10.184:8000/version` → version + git sha.
- Base `rag_config` migrée (7 tables incluant `schema_migrations`).
- Logs JSON visibles via `docker compose logs`.

Aucun secret n'est en clair en base, en logs, ou en config. M2 peut commencer.

---

## Self-review du plan M1

### 1. Couverture du scope M1 (design)

| Livrable scope M1 | Task qui le couvre |
|---|---|
| Squelette `backend/` (pyproject, Dockerfile, layout) | T1 + T4 |
| `config.py` Pydantic Settings | T3 |
| `logging_setup.py` structlog | T2 |
| `main.py` lifespan stub | T17 |
| `db/pool.py` (AsyncpgPool factory + cache LRU) | T11 |
| `db/helpers.py` (fetch_one/all/execute, transaction CM) | T11 |
| `db/migrations.py` (runner SQL idempotent) | T6 |
| Migration 001 (workspaces + indexer_configs + schema_migrations) | T7 (workspaces+indexer) + T6 (schema_migrations) |
| Migration 002 (workspace_sources) | T8 |
| Migration 003 (jobs + indexed_documents) | T9 |
| Migration 004 (oidc_config) | T10 |
| `secrets/resolver.py` (env:// + vault://, cache, invalidation) | T12 + T14 |
| Wrap SDK Harpocrate | T13 |
| `auth/bearer.py` master key | T15 |
| `api/health.py` (/health, /version) | T16 |
| Fixtures pytest (pg_container, etc.) | T5 (base) + T11/T17 (extensions) |
| Quality gate + deploy LXC 303 | T18 |

Couverture **complète**.

### 2. Cohérence des signatures

- `SecretResolver(harpocrate_clients=...)` : signature consistante T12/T13/T14/T17.
- `WorkspacePoolRegistry(config_dsn=..., admin_dsn=..., max_workspace_pools=..., min_size=..., max_size=...)` : utilisé en T11 et T17 — match.
- `run_migrations(pool, migrations_dir)` : signature stable T6, T17.
- `require_master_key(request)` : dependency FastAPI, consommée via `Depends()` en T15 et plus tard M2.
- `parse_ref(value) -> ParsedRef | None` : stable T12, T14.
- `build_app(*, version, git_sha, resolver_factory, migrations_dir)` : T17.

### 3. Placeholders ? Pas de TBD/TODO/FIXME dans le plan.

Les sections marquées "À adapter en M5" / "vide jusqu'à M5" sont **explicites** sur leur statut et leur jalon de complétion. Pas des placeholders au sens "rempli plus tard sans cible" — ils ont leur jalon.

### 4. Risques identifiés

- **SDK Harpocrate non téléchargeable depuis le poste Windows** (réseau vers vault.yoops.org KO) → l'exécutant local devra skip les tests touchant `HarpocrateVaultClient` et compter sur l'exécution LXC 303. Test prévu : `test_harpocrate_client_implements_protocol` ne fait que vérifier la classe sans l'instancier, donc OK même sans SDK installé. Le `uv sync` lui-même échouera sans wheel — mais le pattern dans `[tool.uv.sources]` impose la présence. **Mitigation** : documenter explicitement dans `backend/README.md` (déjà fait T1.4 partiellement, à compléter si nécessaire).

- **Timing fixture `pg_container` (scope session)** : un seul container pour toute la session pytest. Les tests doivent nettoyer (TRUNCATE / DROP IF EXISTS) entre eux pour isoler. Pattern visible dans les tests T7-T11.

### 5. Estimation

- T1-T2 : ~1h chacun (squelette + structlog avec tests)
- T3 : ~1h30 (Pydantic Settings avec validators non triviaux)
- T4 : ~1h (Dockerfile, vérification limitée au LXC)
- T5 : ~30min (conftest minimal)
- T6 : ~1h30 (migration runner + tests d'idempotence)
- T7-T10 : ~30min chacune (migrations + tests structure)
- T11 : ~2h (helpers + pool registry + LRU)
- T12-T14 : ~3h total (SecretResolver complet en 3 itérations TDD)
- T15-T16 : ~1h chacune
- T17 : ~1h30 (main + lifespan + intégration)
- T18 : ~1h (Caddyfile + cleanup + deploy + smoke + QG)

**Total estimé : ~16-18h de travail concentré (≈ 2-3 jours réels avec relecture, debug, mise en route LXC).**
