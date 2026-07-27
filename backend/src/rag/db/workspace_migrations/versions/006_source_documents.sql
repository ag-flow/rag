-- Migration workspace 006 — stockage du contenu source des documents poussés
--
-- Les documents poussés (docflow, API REST) n'ont pas de source git
-- re-clonable : sans copie locale du source, un changement de chunking ou
-- d'indexeur est irrécupérable (fiche bug aced5d5e). Cette table est la
-- matière première du job de réindexation : alimentée au push, purgée au
-- delete, relue par _execute_reindex_job. Les fichiers issus des sources git
-- n'y figurent pas (le re-clone est leur source de vérité).
--
-- IF NOT EXISTS : reset_workspace_schema (changement d'indexeur) préserve
-- cette table mais rejoue toutes les migrations depuis 001 — la re-création
-- doit être un no-op, le contenu doit survivre au reset.
CREATE TABLE IF NOT EXISTS source_documents (
    path         TEXT PRIMARY KEY,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title        TEXT,
    source_url   TEXT,
    pushed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
