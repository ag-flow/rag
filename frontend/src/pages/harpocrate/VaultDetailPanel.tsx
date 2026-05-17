import { useTranslation } from "react-i18next";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useVault } from "@/hooks/useHarpocrateVaults";
import { VaultHeader } from "@/pages/harpocrate/VaultHeader";
import { VaultDetailTab } from "@/pages/harpocrate/VaultDetailTab";

interface VaultDetailPanelProps {
  vaultId: string;
}

export function VaultDetailPanel({ vaultId }: VaultDetailPanelProps) {
  const { t } = useTranslation("harpocrate");
  const { data: vault, isLoading, isError } = useVault(vaultId);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !vault) {
    return (
      <div className="p-6 text-sm text-rose-600">
        Erreur lors du chargement du coffre.
      </div>
    );
  }

  return (
    <div className="px-7 py-5">
      <div className="max-w-[760px]">
        <VaultHeader vault={vault} />

        <Tabs defaultValue="detail" className="mt-4">
          <TabsList>
            <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
            <TabsTrigger value="secrets">{t("tabs.secrets")}</TabsTrigger>
            <TabsTrigger value="info">{t("tabs.info")}</TabsTrigger>
          </TabsList>

          <TabsContent value="detail">
            <VaultDetailTab
              vault={vault}
              onReplaceApiKey={() => alert("T10 : ReplaceApiKeyDialog à venir")}
              onReveal={() => alert("T10 : RevealApiKeyDialog à venir")}
              onRetire={() => alert("T10 : RetireVaultDialog à venir")}
            />
          </TabsContent>

          <TabsContent value="secrets">
            <div className="text-sm text-slate-400 italic py-6">
              Onglet Secrets — T8 à venir.
            </div>
          </TabsContent>

          <TabsContent value="info">
            <div className="text-sm text-slate-400 italic py-6">
              Onglet Info wallet — T9 à venir.
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
