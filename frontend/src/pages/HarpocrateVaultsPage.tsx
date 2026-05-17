import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useVaults } from "@/hooks/useHarpocrateVaults";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { VaultsList } from "@/pages/harpocrate/VaultsList";
import { VaultsEmptyState } from "@/pages/harpocrate/VaultsEmptyState";
import { VaultDetailPanel } from "@/pages/harpocrate/VaultDetailPanel";

export function HarpocrateVaultsPage() {
  const { t } = useTranslation("harpocrate");
  const { data, isLoading } = useVaults();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("vault");
  const [createOpen, setCreateOpen] = useState(false);

  // Auto-sélection au premier load : default ou premier de la liste.
  useEffect(() => {
    if (isLoading) return;
    if (selectedId) return;
    if (!data || data.length === 0) return;
    const defaultVault = data.find((v) => v.is_default) ?? data[0];
    if (defaultVault) {
      setSearchParams({ vault: defaultVault.id }, { replace: true });
    }
  }, [data, isLoading, selectedId, setSearchParams]);

  const handleSelect = (id: string) => {
    setSearchParams({ vault: id }, { replace: true });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  const vaults = data ?? [];

  // État vide : aucun coffre → on remplit tout l'écran avec l'empty state.
  if (vaults.length === 0) {
    return (
      <div className="flex h-full">
        <VaultsEmptyState onCreate={() => setCreateOpen(true)} />
        {/* T7 : <CreateVaultDialog open={createOpen} onOpenChange={setCreateOpen} /> */}
        {createOpen ? null : null}
      </div>
    );
  }

  return (
    <div className="flex h-full bg-slate-50">
      <VaultsList
        selectedId={selectedId}
        onSelect={handleSelect}
        onCreate={() => setCreateOpen(true)}
      />
      <main className="flex-1 bg-white">
        {selectedId ? (
          <VaultDetailPanel vaultId={selectedId} />
        ) : (
          <div className="flex h-full items-center justify-center text-slate-400 italic text-sm">
            {t("page.no_selection")}
          </div>
        )}
      </main>
      {/* T7 : <CreateVaultDialog open={createOpen} onOpenChange={setCreateOpen} /> */}
      {createOpen ? null : null}
    </div>
  );
}
