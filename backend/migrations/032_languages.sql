-- Migration 032 — référentiel global des langues/cultures (spec 14)

CREATE TABLE languages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code       TEXT NOT NULL UNIQUE,       -- BCP 47, ex: "fr-FR", "en-US"
    label      TEXT NOT NULL,              -- libellé lisible
    built_in   BOOLEAN NOT NULL DEFAULT false,  -- true = non supprimable
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO languages (code, label, built_in) VALUES
    ('fr-FR', 'Français (France)',                              true),
    ('fr-BE', 'Français (Belgique)',                            true),
    ('fr-CH', 'Français (Suisse)',                              true),
    ('en-US', 'English (United States)',                        true),
    ('en-GB', 'English (United Kingdom)',                       true),
    ('en-AU', 'English (Australia)',                            true),
    ('de-DE', 'Deutsch (Deutschland)',                          true),
    ('de-AT', 'Deutsch (Österreich)',                           true),
    ('de-CH', 'Deutsch (Schweiz)',                              true),
    ('es-ES', 'Español (España)',                               true),
    ('es-MX', 'Español (México)',                               true),
    ('pt-BR', 'Português (Brasil)',                             true),
    ('pt-PT', 'Português (Portugal)',                           true),
    ('it-IT', 'Italiano (Italia)',                              true),
    ('nl-NL', 'Nederlands (Nederland)',                         true),
    ('pl-PL', 'Polski (Polska)',                                true),
    ('cs-CZ', 'Čeština (Česká republika)',                      true),
    ('hu-HU', 'Magyar (Magyarország)',                          true),
    ('ro-RO', 'Română (România)',                               true),
    ('zh-CN', '中文 (简体)',                                     true),
    ('zh-TW', '中文 (繁體)',                                     true),
    ('ja-JP', '日本語 (日本)',                                   true),
    ('ko-KR', '한국어 (대한민국)',                                true),
    ('ar-SA', 'العربية (المملكة العربية السعودية)',              true)
ON CONFLICT (code) DO NOTHING;
