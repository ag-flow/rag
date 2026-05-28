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
  const [headerErrors, setHeaderErrors] = useState<Record<number, string>>({});

  const hasReservedError = Object.keys(headerErrors).length > 0;

  function validateHeader(idx: number, headerName: string) {
    if (RESERVED.has(headerName.toLowerCase())) {
      setHeaderErrors((e) => ({
        ...e,
        [idx]: t("webhooks.reserved_error"),
      }));
    } else {
      setHeaderErrors((e) => {
        const copy = { ...e };
        delete copy[idx];
        return copy;
      });
    }
  }

  function addHeader() {
    setHeaders((h) => [...h, { name: "", value: "", vault: null, enabled: true }]);
  }

  function removeHeader(idx: number) {
    setHeaders((h) => h.filter((_, i) => i !== idx));
    setHeaderErrors((e) => {
      const copy = { ...e };
      delete copy[idx];
      return copy;
    });
  }

  function updateHeader(
    idx: number,
    field: keyof WebhookHeaderIn,
    value: string | boolean | null,
  ) {
    setHeaders((h) =>
      h.map((item, i) => (i === idx ? { ...item, [field]: value } : item)),
    );
  }

  function handleSubmit() {
    onSubmit({ name, url, enabled: true, headers });
  }

  const canSubmit = name.trim() && url.trim() && !hasReservedError && !loading;

  return (
    <div className="space-y-4">
      <div>
        <Label>{t("webhooks.name")}</Label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="agflow-notify"
        />
      </div>
      <div>
        <Label>{t("webhooks.url")}</Label>
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://..."
        />
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
                  onBlur={(e) => validateHeader(i, e.target.value)}
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
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => removeHeader(i)}
              >
                &times;
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            type="button"
            onClick={addHeader}
          >
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
