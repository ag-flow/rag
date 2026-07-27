-- Migration 086 — template d'URL optionnel par modèle du registre
--
-- Cas d'usage : Azure OpenAI où le nom de DÉPLOIEMENT diffère du nom de
-- modèle. Le template porte l'URL d'appel COMPLÈTE de la capacité du modèle
-- (placeholders {url} ou {base_url}, et {model}), et prime sur le masque du
-- provider (référentiel services/provider_urls.py).
-- Ex. : {url}/openai/deployments/mon-deploiement/embeddings?api-version=2024-02-01

ALTER TABLE model_dimensions ADD COLUMN url_template TEXT;
