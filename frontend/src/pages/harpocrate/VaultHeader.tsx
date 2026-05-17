import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTestConnection, useLastTestResult } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/components/ui/use-toast";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface VaultHeaderProps {
  vault: VaultSummary;
}

export function VaultHeader({ vault }: VaultHeaderProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const testMutation = useTestConnection(vault.id);
  const lastTest = useLastTestResult(vault.id);

  const handleTest = () => {
    testMutation.mutate(undefined, {
      onSuccess: (result) => {
        toast({
          title: result.ok ? t("header.badge_healthy") : t("header.badge_auth_ko"),
          description: result.detail,
          variant: result.ok ? "default" : "destructive",
        });
      },
    });
  };

  return (
    <div className="flex items-start justify-between pb-4 border-b border-slate-200">
      <div>
        <div className="flex items-center gap-2.5">
          <h3 className="text-lg font-semibold text-slate-900 m-0">{vault.name}</h3>
          {vault.is_default && (
            <Badge
              variant="secondary"
              className="bg-amber-100 text-amber-800 hover:bg-amber-100"
            >
              {t("header.badge_default")}
            </Badge>
          )}
          {lastTest && (
            <Badge
              variant="secondary"
              className={
                lastTest.ok
                  ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                  : "bg-rose-100 text-rose-800 hover:bg-rose-100"
              }
            >
              {lastTest.ok ? t("header.badge_healthy") : t("header.badge_auth_ko")}
            </Badge>
          )}
        </div>
        <div className="text-sm text-slate-500 mt-1">
          {vault.label} · {vault.base_url}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button onClick={handleTest} disabled={testMutation.isPending}>
          {t("header.test")}
        </Button>
        <Button variant="outline" size="icon" aria-label="More actions">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
