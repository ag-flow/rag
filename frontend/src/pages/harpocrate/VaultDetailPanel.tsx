import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useVault, useVaultWalletInfo } from "@/hooks/useHarpocrateVaults";
import { VaultHeader } from "@/pages/harpocrate/VaultHeader";
import { VaultDetailTab } from "@/pages/harpocrate/VaultDetailTab";
import { VaultSecretsTab } from "@/pages/harpocrate/VaultSecretsTab";
import { VaultWalletInfoTab } from "@/pages/harpocrate/VaultWalletInfoTab";
import { RevealApiKeyDialog } from "@/pages/harpocrate/RevealApiKeyDialog";
import { RetireVaultDialog } from "@/pages/harpocrate/RetireVaultDialog";
import { VaultApikeysTab } from "@/pages/harpocrate/VaultApikeysTab";

type DialogKind = "reveal" | "retire" | null;

interface VaultDetailPanelProps {
  vaultId: string;
}

export function VaultDetailPanel({ vaultId }: VaultDetailPanelProps) {
  const { t } = useTranslation("harpocrate");
  const { data: vault, isLoading, isError } = useVault(vaultId);
  const [dialogOpen, setDialogOpen] = useState<DialogKind>(null);
  const [, setSearchParams] = useSearchParams();

  // On charge le wallet info pour disposer du nom du wallet distant et l'afficher
  // dans le RetireVaultDialog. Si le fetch échoue ou est en cours, on retombe sur
  // la branche `warning_without_wallet`.
  const { data: walletInfo } = useVaultWalletInfo(vaultId, true);

  function handleRetired() {
    // Après suppression : retirer le ?vault=<id> de l'URL pour revenir à l'état
    // "aucun coffre sélectionné".
    setSearchParams({}, { replace: true });
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !vault) {
    return <div className="p-6 text-sm text-rose-600">{t("detail.load_error")}</div>;
  }

  return (
    <div className="px-7 py-5">
      <div className="max-w-[760px]">
        <VaultHeader vault={vault} onRetire={() => setDialogOpen("retire")} />

        <Tabs defaultValue="detail" className="mt-4">
          <TabsList>
            <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
            <TabsTrigger value="secrets">{t("tabs.secrets")}</TabsTrigger>
            <TabsTrigger value="info">{t("tabs.info")}</TabsTrigger>
            <TabsTrigger value="apikeys">{t("tabs.apikeys")}</TabsTrigger>
          </TabsList>

          <TabsContent value="detail">
            <VaultDetailTab
              vault={vault}
              onReveal={() => setDialogOpen("reveal")}
              onRetire={() => setDialogOpen("retire")}
            />
          </TabsContent>

          <TabsContent value="secrets">
            <VaultSecretsTab vaultId={vault.id} />
          </TabsContent>

          <TabsContent value="info">
            <VaultWalletInfoTab vaultId={vault.id} />
          </TabsContent>

          <TabsContent value="apikeys">
            <VaultApikeysTab vaultId={vault.id} vaultName={vault.name} />
          </TabsContent>
        </Tabs>
      </div>

      <RevealApiKeyDialog
        vaultId={vault.id}
        open={dialogOpen === "reveal"}
        onOpenChange={(o) => setDialogOpen(o ? "reveal" : null)}
      />
      <RetireVaultDialog
        vault={vault}
        walletName={walletInfo?.wallet_name ?? null}
        open={dialogOpen === "retire"}
        onOpenChange={(o) => setDialogOpen(o ? "retire" : null)}
        onRetired={handleRetired}
      />
    </div>
  );
}
