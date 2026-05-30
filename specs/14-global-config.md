# RAG Service — Configuration Globale

## Principe

La configuration globale regroupe les référentiels partagés entre tous les workspaces. Elle est gérée exclusivement via l'IHM (rôle `rag-admin`) ou via l'API d'administration.

---

## Langues et cultures — table `languages`

Référentiel global des langues/cultures disponibles pour les prompt templates. Pré-peuplé à l'installation, extensible par l'administrateur.

```sql
CREATE TABLE languages (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code        TEXT NOT NULL UNIQUE,   -- code culture, ex: "fr-FR", "en-US", "pt-BR"
  label       TEXT NOT NULL,          -- libellé lisible, ex: "Français (France)"
  built_in    BOOLEAN DEFAULT false,  -- true = fourni par le service, non supprimable
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Cultures pré-peuplées

```sql
INSERT INTO languages (code, label, built_in) VALUES
  ('fr-FR', 'Français (France)',            true),
  ('fr-BE', 'Français (Belgique)',           true),
  ('fr-CH', 'Français (Suisse)',             true),
  ('en-US', 'English (United States)',       true),
  ('en-GB', 'English (United Kingdom)',      true),
  ('en-AU', 'English (Australia)',           true),
  ('de-DE', 'Deutsch (Deutschland)',         true),
  ('de-AT', 'Deutsch (Österreich)',          true),
  ('de-CH', 'Deutsch (Schweiz)',             true),
  ('es-ES', 'Español (España)',              true),
  ('es-MX', 'Español (México)',              true),
  ('pt-BR', 'Português (Brasil)',            true),
  ('pt-PT', 'Português (Portugal)',          true),
  ('it-IT', 'Italiano (Italia)',             true),
  ('nl-NL', 'Nederlands (Nederland)',        true),
  ('pl-PL', 'Polski (Polska)',               true),
  ('cs-CZ', 'Čeština (Česká republika)',     true),
  ('hu-HU', 'Magyar (Magyarország)',         true),
  ('ro-RO', 'Română (România)',              true),
  ('zh-CN', '中文 (简体)',                    true),
  ('zh-TW', '中文 (繁體)',                    true),
  ('ja-JP', '日本語 (日本)',                  true),
  ('ko-KR', '한국어 (대한민국)',               true),
  ('ar-SA', 'العربية (المملكة العربية السعودية)', true);
```

---

## Règles

- Les cultures `built_in = true` ne peuvent pas être supprimées
- L'administrateur peut ajouter n'importe quelle culture personnalisée (`built_in = false`)
- Les cultures personnalisées peuvent être supprimées si elles ne sont pas référencées par un prompt template actif
- Le code suit la norme BCP 47 (`language-REGION`)

---

## API

```
GET    /config/languages              — lister toutes les langues
POST   /config/languages              — ajouter une langue personnalisée
DELETE /config/languages/{code}       — supprimer (erreur si built_in ou référencée)
```

### Ajouter une langue

```bash
curl -X POST https://rag.yoops.org/config/languages \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -d '{
    "code": "vi-VN",
    "label": "Tiếng Việt (Việt Nam)"
  }'
```

---

## Lien avec les prompt templates

Le champ `language` de la table `prompt_templates` référence le `code` de cette table :

```sql
ALTER TABLE prompt_templates
  ADD CONSTRAINT fk_language
  FOREIGN KEY (language) REFERENCES languages(code);
```

Dans l'IHM de création d'un prompt template, le sélecteur de langue est alimenté par cette table.
