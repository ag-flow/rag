import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useVaults } from "@/hooks/useHarpocrateVaults";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface VaultsListProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
}

export function VaultsList({ selectedId, onSelect, onCreate }: VaultsListProps) {
  const { t } = useTranslation("harpocrate");
  const { data, isLoading } = useVaults();

  return (
    <aside className="w-[240px] flex-shrink-0 border-r border-slate-200 bg-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <span className="font-semibold text-slate-900">{t("list.header")}</span>
        <Button size="sm" onClick={onCreate} className="h-7 px-2.5 text-xs">
          {t("list.new")}
        </Button>
      </div>

      <div className="py-2">
        {isLoading ? (
          <div className="px-4 py-6 flex justify-center">
            <LoadingSpinner />
          </div>
        ) : (
          (data ?? []).map((vault: VaultSummary) => (
            <VaultsListItem
              key={vault.id}
              vault={vault}
              active={vault.id === selectedId}
              onSelect={() => onSelect(vault.id)}
            />
          ))
        )}
      </div>
    </aside>
  );
}

interface VaultsListItemProps {
  vault: VaultSummary;
  active: boolean;
  onSelect: () => void;
}

function VaultsListItem({ vault, active, onSelect }: VaultsListItemProps) {
  const { t } = useTranslation("harpocrate");
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full text-left px-3 py-2 mx-1 rounded-r transition-colors block",
        active
          ? "bg-sky-50 border-l-[3px] border-sky-600"
          : "hover:bg-slate-50 border-l-[3px] border-transparent",
      )}
    >
      <div className="flex items-center justify-between">
        <span className={cn("font-medium truncate", active ? "text-slate-900" : "text-slate-700")}>
          {vault.name}
        </span>
        <span className={cn("text-[10px] ml-2", active ? "text-emerald-600" : "text-slate-300")}>
          ●
        </span>
      </div>
      <div className="text-xs text-slate-500 mt-0.5 truncate">
        {vault.is_default ? `${t("list.default_marker")} · ${vault.label}` : vault.label}
      </div>
    </button>
  );
}
