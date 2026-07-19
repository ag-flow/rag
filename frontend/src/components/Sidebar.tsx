// frontend/src/components/Sidebar.tsx
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutGrid,
  Database,
  FileCode,
  Scissors,
  Send,
  Search,
  Settings,
  KeyRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useVaultExpiries } from "@/hooks/useHarpocrateVaults";
import { worstExpiryStatus } from "@/lib/vault-expiry";

interface NavItemProps {
  to: string;
  icon: ReactNode;
  label: string;
  disabled?: boolean;
  badge?: ReactNode;
}

function NavItem({ to, icon, label, disabled = false, badge }: NavItemProps) {
  if (disabled) {
    return (
      <div
        className="mx-2 my-0.5 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-slate-500 cursor-not-allowed select-none"
        aria-disabled="true"
      >
        <span className="text-slate-400 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "mx-2 my-0.5 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-primary text-primary-foreground font-bold"
            : "text-slate-900 font-semibold hover:bg-slate-100",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              "[&>svg]:h-4 [&>svg]:w-4",
              isActive ? "text-primary-foreground" : "text-slate-700",
            )}
          >
            {icon}
          </span>
          <span>{label}</span>
          {badge}
        </>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { t } = useTranslation("nav");
  const { data: expiries } = useVaultExpiries();
  const vaultAlert = worstExpiryStatus(expiries ?? []);
  const vaultBadge =
    vaultAlert === "expired" || vaultAlert === "expiring" ? (
      <span
        aria-label={t("alerts.vault_key_expiry")}
        title={t("alerts.vault_key_expiry")}
        className={
          "ml-auto h-2 w-2 rounded-full " +
          (vaultAlert === "expired" ? "bg-rose-500" : "bg-amber-400")
        }
      />
    ) : undefined;

  return (
    <aside className="w-[220px] flex-shrink-0 border-r border-slate-200 bg-zinc-50 flex flex-col">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
        <div className="h-6 w-6 rounded-md bg-gradient-to-br from-sky-600 to-sky-500" />
        <span className="font-semibold text-slate-900">ag-flow.rag</span>
      </div>

      <nav className="flex-1 py-3">
        <div className="px-5 pt-3 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.administration")}
        </div>
        <NavItem to="/workspaces" icon={<LayoutGrid />} label={t("items.workspaces")} />
        <NavItem to="/models" icon={<Database />} label={t("items.models")} />
        <NavItem to="/prompts" icon={<FileCode />} label={t("items.prompts")} />
        <NavItem
          to="/chunking-strategies"
          icon={<Scissors />}
          label={t("items.chunking_strategies")}
        />

        <div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.usage")}
        </div>
        <NavItem to="/push" icon={<Send />} label={t("items.push")} />
        <NavItem to="/mcp" icon={<Search />} label={t("items.mcp")} />

        <div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.configuration")}
        </div>
        <NavItem
          to="/settings/harpocrate-vaults"
          icon={<Settings />}
          label={t("items.harpocrate_vaults")}
          badge={vaultBadge}
        />
        <NavItem to="/settings/api-keys" icon={<KeyRound />} label={t("items.api_keys")} />
        <NavItem to="/settings/oidc-config" icon={<KeyRound />} label={t("items.oidc_config")} />
      </nav>
    </aside>
  );
}
