import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { VaultEndpoint } from "@/lib/vault-endpoints.types";

export const FALLBACK_NONE = "__none__";

interface Props {
  /** Endpoint en cours d'édition (la section n'existe qu'en édition). */
  endpoint: VaultEndpoint;
  /** Tous les endpoints du coffre (la liste est filtrée ici). */
  endpoints: VaultEndpoint[];
  fallbackId: string;
  onFallbackChange: (v: string) => void;
  failureThreshold: string;
  onFailureThresholdChange: (v: string) => void;
  cooldownSeconds: string;
  onCooldownChange: (v: string) => void;
}

/** Sélecteur d'endpoint de fallback + paramètres du circuit breaker.
 *
 * Éligibles : les endpoints du même coffre, hors soi-même et hors endpoints
 * déclarant déjà leur propre fallback (un seul niveau). La compatibilité de
 * vectorisation (même modèle d'embedding) est signalée ici à titre indicatif —
 * le backend reste l'autorité (422 pédagogique). */
export function EndpointFallbackSection({
  endpoint,
  endpoints,
  fallbackId,
  onFallbackChange,
  failureThreshold,
  onFailureThresholdChange,
  cooldownSeconds,
  onCooldownChange,
}: Props) {
  const { t } = useTranslation("harpocrate");
  const eligible = endpoints.filter((e) => e.id !== endpoint.id && e.fallback_endpoint_id == null);

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">{t("endpoints.fallback_intro")}</p>
      <div>
        <Label className="text-xs text-slate-600">{t("endpoints.fallback_select")}</Label>
        <Select value={fallbackId} onValueChange={onFallbackChange}>
          <SelectTrigger className="mt-1" aria-label={t("endpoints.fallback_select")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FALLBACK_NONE}>{t("endpoints.fallback_none")}</SelectItem>
            {eligible.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {e.label}
                {e.indexer.model !== endpoint.indexer.model
                  ? ` — ${t("endpoints.fallback_incompatible_hint")}`
                  : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="mt-1 text-xs text-slate-400">{t("endpoints.fallback_vector_rule")}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs text-slate-600">{t("endpoints.fallback_threshold")}</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={failureThreshold}
            onChange={(e) => onFailureThresholdChange(e.target.value)}
            className="mt-1"
            aria-label={t("endpoints.fallback_threshold")}
          />
        </div>
        <div>
          <Label className="text-xs text-slate-600">{t("endpoints.fallback_cooldown")}</Label>
          <Input
            type="number"
            min={1}
            max={3600}
            value={cooldownSeconds}
            onChange={(e) => onCooldownChange(e.target.value)}
            className="mt-1"
            aria-label={t("endpoints.fallback_cooldown")}
          />
        </div>
      </div>
      <p className="text-xs text-slate-400">{t("endpoints.fallback_breaker_help")}</p>
    </div>
  );
}
