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
