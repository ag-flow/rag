-- Migration 038 — modèles Voyage AI accessibles via Azure AI Foundry

INSERT INTO model_dimensions (provider, model, dimension, service) VALUES
    ('azure-foundry', 'voyage-3.5',    1024, 'voyage'),
    ('azure-foundry', 'voyage-4',      1024, 'voyage'),
    ('azure-foundry', 'voyage-4-lite',  512, 'voyage')
ON CONFLICT DO NOTHING;
