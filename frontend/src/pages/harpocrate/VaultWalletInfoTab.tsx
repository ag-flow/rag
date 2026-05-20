import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useVaultWalletInfo } from "@/hooks/useHarpocrateVaults";

const KNOWN_PERMISSIONS = ["read", "write", "add", "remove"] as const;

interface VaultWalletInfoTabProps {
  vaultId: string;
}

export function VaultWalletInfoTab({ vaultId }: VaultWalletInfoTabProps) {
  const { t } = useTranslation("harpocrate");
  const { data, isLoading, isError, refetch, isRefetching } = useVaultWalletInfo(vaultId, true);

  if (isError) {
    return (
      <div className="rounded border border-rose-200 bg-rose-50 p-4">
        <h4 className="mb-1 font-semibold text-rose-800">{t("info.loading_error_title")}</h4>
        <p className="mb-3 text-sm text-rose-700">{t("info.loading_error_body")}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isRefetching}>
          {t("info.retry")}
        </Button>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
      </div>
    );
  }

  const presentPerms = new Set(data.permissions);

  return (
    <div className="space-y-5">
      {/* Section Wallet */}
      <Section title={t("info.wallet_section")}>
        <Row label={t("info.wallet_name")}>
          {data.wallet_name ? (
            <span className="font-medium text-slate-900">{data.wallet_name}</span>
          ) : (
            <span className="text-slate-400">{t("info.wallet_name_unset")}</span>
          )}
        </Row>
        <Row label={t("info.wallet_id")}>
          <span className="font-mono text-xs text-slate-700">{data.wallet_id}</span>
        </Row>
      </Section>

      {/* Section API key */}
      <Section title={t("info.apikey_section")}>
        <Row label={t("info.apikey_id")}>
          <span className="font-mono text-slate-900">{data.api_key_id}</span>
        </Row>
        <Row label={t("info.permissions")}>
          <div className="flex flex-wrap gap-1.5">
            {KNOWN_PERMISSIONS.map((perm) => {
              const present = presentPerms.has(perm);
              return (
                <Badge
                  key={perm}
                  variant="secondary"
                  className={cn(
                    "text-xs",
                    present
                      ? "bg-sky-100 text-sky-800 hover:bg-sky-100"
                      : "bg-slate-100 text-slate-400 line-through hover:bg-slate-100",
                  )}
                >
                  {perm}
                </Badge>
              );
            })}
          </div>
        </Row>
        <Row label={t("info.expires_at")}>
          <ExpiresCell expiresAt={data.api_key_expires_at} />
        </Row>
      </Section>

      {/* Footer note */}
      <div className="rounded-r border-l-2 border-slate-300 bg-slate-50 px-3 py-2 text-xs italic text-slate-400">
        {t("info.footer_note")}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-600">
        {title}
      </h4>
      <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] items-baseline gap-4 text-sm">
      <span className="text-slate-500">{label}</span>
      <div>{children}</div>
    </div>
  );
}

function ExpiresCell({ expiresAt }: { expiresAt: string | null }) {
  const { t } = useTranslation("harpocrate");

  if (!expiresAt) {
    return <span className="italic text-slate-500">{t("info.expires_never")}</span>;
  }

  const date = new Date(expiresAt);
  const now = Date.now();
  const diffMs = date.getTime() - now;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  const formattedDate = date.toISOString().slice(0, 10);

  if (diffMs < 0) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-slate-900">{formattedDate}</span>
        <Badge variant="secondary" className="bg-rose-100 text-rose-800 hover:bg-rose-100">
          {t("info.expired")}
        </Badge>
      </div>
    );
  }

  if (diffDays < 30) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-slate-900">{formattedDate}</span>
        <Badge variant="secondary" className="bg-orange-100 text-orange-800 hover:bg-orange-100">
          {t("info.expires_soon")}
        </Badge>
      </div>
    );
  }

  const months = Math.floor(diffDays / 30);
  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-900">{formattedDate}</span>
      <Badge variant="secondary" className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
        {t("info.expires_in_months", { count: months })}
      </Badge>
    </div>
  );
}
