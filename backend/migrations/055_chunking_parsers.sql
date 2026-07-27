-- Migration 055 — registre des parsers de régions (chunking, passe 1)
--
-- Table de référence pour l'IHM : liste les parsers de régions disponibles
-- côté code (protocole RegionParser, registre `region_registry.py`). Un seul
-- parser en v1 : markdown. Les stratégies y feront référence via la future
-- colonne `chunking_strategies.parser_slug` (feature routage de régions).
-- Spec : « Chunking : parser de régions, routage intra-document, stratégies
-- par utilisateur » §2.

CREATE TABLE chunking_parsers (
    slug  TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO chunking_parsers (slug, label) VALUES ('markdown', 'Markdown');
