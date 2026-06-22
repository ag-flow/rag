-- Migration 039 — model_dimensions : source de vérité des limites de tokens
--
-- ADR 0001 §3 (axe 3) : le chunking structure-aware borne en TOKENS, pas en
-- caractères. La limite par modèle devient une colonne requêtable (et non plus
-- de la prose dans pricing.yml). Le plafond dur effectif est dérivé au runtime :
-- floor(safety_factor * max_input_tokens).
--
-- Politique de seed CONSERVATRICE : défaut 8192 (plancher documenté partagé par
-- la majorité des modèles d'embedding). On n'ABAISSE que les modèles dont la
-- limite réelle connue est inférieure (jamais de relèvement optimiste qui
-- risquerait un dépassement silencieux). L'admin peut ajuster par modèle.

ALTER TABLE model_dimensions
    ADD COLUMN max_input_tokens INT     NOT NULL DEFAULT 8192 CHECK (max_input_tokens > 0),
    ADD COLUMN token_char_ratio NUMERIC NOT NULL DEFAULT 4.0  CHECK (token_char_ratio > 0);

-- Modèles à limite connue inférieure au défaut conservateur.
UPDATE model_dimensions SET max_input_tokens = 512
    WHERE provider = 'ollama' AND model = 'mxbai-embed-large';
UPDATE model_dimensions SET max_input_tokens = 2048
    WHERE provider = 'gemini' AND model = 'gemini-embedding-001';
