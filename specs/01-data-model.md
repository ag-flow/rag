# RAG Service — Modèle de données

## Base de configuration : `rag_config`

Base PostgreSQL centrale qui stocke le paramétrage du service. Aucun secret en clair — uniquement des références logiques vers Harpocrate.

---

### Table `workspaces`

```sql
CREATE TABLE workspaces (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  api_key_hash  TEXT NOT NULL,        -- hash bcrypt de l'api_key workspace
  rag_cnx       TEXT NOT NULL,        -- connection string base pgvector dédiée
  rag_base      TEXT NOT NULL,        -- nom de la base pgvector
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);
```

---

### Table `indexer_configs`

```sql
CREATE TABLE indexer_configs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider      TEXT NOT NULL,        -- "openai" | "voyage" | "ollama"
  model         TEXT NOT NULL,        -- ex: "text-embedding-3-small"
  base_url      TEXT,                 -- null sauf ollama
  api_key_ref   TEXT,                 -- clé logique Harpocrate, ex: "openai_embedding_key"
  dimension     INT NOT NULL,         -- résolu à la création selon provider+model
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

La `api_key_ref` est une **clé logique opaque** — Harpocrate fait la résolution vers le secret réel. Le service RAG ne connaît jamais le path physique.

---

### Table `workspace_sources`

```sql
CREATE TABLE workspace_sources (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  type           TEXT NOT NULL DEFAULT 'git',   -- "git" | extensible
  config         JSONB NOT NULL,                -- voir détail ci-dessous
  last_indexed_at TIMESTAMPTZ,
  created_at     TIMESTAMPTZ DEFAULT now()
);
```

Contenu de `config` pour une source git :

```json
{
  "url": "https://github.com/gael/harpocrate",
  "branch": "main",
  "auth_ref": "github_token",
  "include": ["**/*.md"],
  "exclude": []
}
```

Le champ `auth_ref` suit le même pattern que `api_key_ref` — clé logique Harpocrate.

---

### Table `index_jobs`

```sql
CREATE TABLE index_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id),
  source_id       UUID REFERENCES workspace_sources(id),
  triggered_by    TEXT NOT NULL,    -- "webhook" | "manual" | "push" | "schedule"
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
  files_changed   INT DEFAULT 0,
  files_skipped   INT DEFAULT 0,    -- dédupliqués via hash
  error_message   TEXT,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  duration_ms     INT
);
```

---

### Table `indexed_documents`

```sql
CREATE TABLE indexed_documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  path          TEXT NOT NULL,          -- path relatif, clé métier
  content_hash  TEXT NOT NULL,          -- SHA-256 du contenu
  indexer_used  TEXT NOT NULL,          -- "openai/text-embedding-3-small"
  indexed_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, path)
);
```

---

## Base vectorielle : `rag_{workspace_name}`

Une base pgvector **dédiée par workspace**. La dimension est fixée à la création selon le provider et le modèle.

```sql
-- Créée automatiquement à la création du workspace
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
  id            SERIAL PRIMARY KEY,
  path          TEXT NOT NULL,
  chunk_index   INT NOT NULL,
  content       TEXT NOT NULL,          -- texte du chunk (utile pour le contexte retourné)
  embedding     vector(1536),           -- dimension injectée selon modèle
  indexed_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(path, chunk_index)
);

CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

## Règle de cohérence

Un workspace ne peut pas changer d'indexeur sans réindexation complète — les dimensions des vecteurs sont incompatibles entre modèles. Voir `02-api-admin.md` pour le comportement de l'API en cas de changement d'indexeur.
