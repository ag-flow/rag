import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { WebhookCreatePayload, WebhookHeaderIn } from "@/lib/webhooks.types";

const RESERVED = new Set([
  "x-correlation-id",
  "x-rag-signature",
  "x-git-repo",
  "x-git-branch",
  "x-git-commit",
]);

interface Props {
  onSubmit: (payload: WebhookCreatePayload) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function WebhookForm({ onSubmit, onCancel, loading }: Props) {
  const { t } = useTranslation("workspace");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState<WebhookHeaderIn[]>([
    { name: "X-Api-Key", value: "", vault: null, enabled: false },
  ]);
  const [touched, setTouched] = useState<Record<number, boolean>>({});

  // Erreurs recalculées à chaque rendu depuis `headers` — jamais stockées
  // par index dans un state séparé, pour éviter tout décalage lors d'un
  // removeHeader qui compacte le tableau.
  const headerErrors: Record<number, string> = {};
  headers.forEach((h, i) => {
    if (touched[i] && RESERVED.has(h.name.toLowerCase())) {
      headerErrors[i] = t("webhooks.reserved_error");
    }
  });

  const hasReservedError = Object.keys(headerErrors).length > 0;

  function validateHeader(idx: number) {
    setTouched((t) => ({ ...t, [idx]: true }));
  }

  function addHeader() {
    setHeaders((h) => [...h, { name: "", value: "", vault: null, enabled: true }]);
    setTouched((t) => ({ ...t, [headers.length]: false }));
  }

  function removeHeader(idx: number) {
    setHeaders((h) => h.filter((_, i) => i !== idx));
    setTouched((t) => {
      const entries = Object.entries(t)
        .map(([k, v]) => [Number(k), v] as const)
        .filter(([i]) => i !== idx)
        .map(([i, v]) => [i > idx ? i - 1 : i, v] as const);
      return Object.fromEntries(entries);
    });
  }

  function updateHeader(idx: number, field: keyof WebhookHeaderIn, value: string | boolean | null) {
    setHeaders((h) => h.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  }

  function handleSubmit() {
    onSubmit({ name, url, enabled: true, headers });
  }

  const canSubmit = name.trim() && url.trim() && !hasReservedError && !loading;

  return (
    <div className="space-y-4">
      <div>
        <Label>{t("webhooks.name")}</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="agflow-notify" />
      </div>
      <div>
        <Label>{t("webhooks.url")}</Label>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
      </div>

      <div>
        <Label>{t("webhooks.headers")}</Label>
        <div className="space-y-2 mt-1">
          {headers.map((h, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="flex-1">
                <Input
                  placeholder={t("webhooks.header_name")}
                  value={h.name}
                  onChange={(e) => updateHeader(i, "name", e.target.value)}
                  onBlur={() => validateHeader(i)}
                />
                {headerErrors[i] !== undefined && (
                  <p className="text-xs text-red-500 mt-1">{headerErrors[i]}</p>
                )}
              </div>
              <Input
                placeholder={t("webhooks.header_value")}
                type="password"
                value={h.value ?? ""}
                className="flex-1"
                onChange={(e) => updateHeader(i, "value", e.target.value)}
              />
              <Button variant="ghost" size="sm" type="button" onClick={() => removeHeader(i)}>
                &times;
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" type="button" onClick={addHeader}>
            {t("webhooks.add_header")}
          </Button>
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <Button variant="outline" onClick={onCancel} type="button">
          {t("webhooks.cancel")}
        </Button>
        <Button onClick={handleSubmit} disabled={!canSubmit} type="button">
          {t("webhooks.save")}
        </Button>
      </div>
    </div>
  );
}
