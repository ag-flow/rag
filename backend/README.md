# rag — Backend

Service d'infrastructure RAG. Spec : `../docs/superpowers/specs/2026-05-14-rag-mvp-implementation-design.md`.

## Quickstart local (Windows)

```powershell
cd backend
./scripts/fetch-harpocrate-sdk.sh    # télécharge le wheel dans vendor/
uv sync                               # installe deps + wheel local
uv run pytest -v
```

## Tests

Les tests d'intégration ciblent le Postgres partagé hébergé sur l'infra de dev
(LXC 303 par défaut), conformément à CLAUDE.md. Une base jetable
`rag_test_<uuid>` est provisionnée par session pytest et droppée en fin de run.

**Variables d'environnement** :

| Variable | Défaut | Rôle |
|---|---|---|
| `TEST_POSTGRES_HOST` | `192.168.10.184` | Host du Postgres de test |
| `TEST_POSTGRES_PORT` | `5432` | Port |
| `TEST_POSTGRES_USER` | `rag` | User avec droit `CREATE DATABASE` |
| `TEST_POSTGRES_PASSWORD` | _(requis)_ | Sans valeur → tests d'intégration sautés |

```powershell
$env:TEST_POSTGRES_PASSWORD = "<password du LXC 303>"
uv run pytest -v
```

Cibles fréquentes :

- Unit (rapides, sans réseau) : `uv run pytest tests/unit -v`
- Intégration (Postgres LXC requis) : `uv run pytest tests/integration -v`
- API : `uv run pytest tests/api -v`
- Smoke (opt-in, providers réels) : `uv run pytest -m smoke -v`
- Couverture : `uv run pytest --cov=src/rag --cov-report=term-missing`

### Smoke opt-in (providers réels)

Les tests smoke valident les providers d'embedding contre les vraies APIs.
Ils sont **skippés par défaut** (`addopts = "-m 'not smoke'"` dans
`pyproject.toml`). Pour les exécuter, définir les env vars correspondantes :

```powershell
$env:OPENAI_API_KEY_TEST = "sk-..."           # OpenAI test key
$env:VOYAGE_API_KEY_TEST = "vk-..."           # Voyage AI test key
$env:OLLAMA_TEST_URL     = "http://192.168.10.80:11434"   # LXC Ollama homelab
uv run pytest -m smoke -v
```

Chaque test skip individuellement si sa variable d'env n'est pas définie.
Coût estimé OpenAI : <$0.001 par run (text-embedding-3-small).

## Lint, format, type check

```powershell
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src/rag
```
