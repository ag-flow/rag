import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useLastTestResult,
  useSetDefaultVault,
  useTestConnection,
} from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface VaultHeaderProps {
  vault: VaultSummary;
  onRetire: () => void;
}

export function VaultHeader({ vault, onRetire }: VaultHeaderProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const testMutation = useTestConnection(vault.id);
  const setDefaultMutation = useSetDefaultVault();
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

  async function handleSetDefault() {
    try {
      await setDefaultMutation.mutateAsync(vault.id);
      toast({
        title: t("menu.set_default_done_toast", { name: vault.name }),
      });
    } catch {
      toast({
        title: t("menu.set_default_error_toast"),
        variant: "destructive",
      });
    }
  }

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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon" aria-label="More actions">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={handleSetDefault}
              disabled={vault.is_default || setDefaultMutation.isPending}
            >
              {t("menu.set_default")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={onRetire}
              className="text-rose-600 focus:text-rose-700 focus:bg-rose-50"
            >
              {t("detail.retire_vault")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
