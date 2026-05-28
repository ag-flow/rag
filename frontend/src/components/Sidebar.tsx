// frontend/src/components/Sidebar.tsx
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LayoutGrid, Database, Send, Search, Settings, KeyRound } from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItemProps {
  to: string;
  icon: ReactNode;
  label: string;
  disabled?: boolean;
}

function NavItem({ to, icon, label, disabled = false }: NavItemProps) {
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
        </>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { t } = useTranslation("nav");

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

        <div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.usage")}
        </div>
        <NavItem to="/push" icon={<Send />} label={t("items.push")} disabled />
        <NavItem to="/mcp" icon={<Search />} label={t("items.mcp")} disabled />

        <div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.configuration")}
        </div>
        <NavItem
          to="/settings/harpocrate-vaults"
          icon={<Settings />}
          label={t("items.harpocrate_vaults")}
        />
        <NavItem to="/settings/oidc-config" icon={<KeyRound />} label={t("items.oidc_config")} />
      </nav>
    </aside>
  );
}
