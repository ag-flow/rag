import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import type { Workspace } from "@/lib/workspaces.types";
import type { WorkspaceGrant } from "@/lib/user-api-keys.types";

interface Props {
  workspaces: Workspace[];
  value: WorkspaceGrant[];
  onChange: (grants: WorkspaceGrant[]) => void;
}

/** Éditeur des droits d'une clé : par workspace, accès + permissions R/W. */
export function GrantsEditor({ workspaces, value, onChange }: Props) {
  const { t } = useTranslation("apikeys");

  const byId = new Map(value.map((g) => [g.workspace_id, g]));

  function toggleWorkspace(wsId: string, granted: boolean) {
    if (granted) {
      onChange([...value, { workspace_id: wsId, can_read: true, can_write: false }]);
    } else {
      onChange(value.filter((g) => g.workspace_id !== wsId));
    }
  }

  function togglePerm(wsId: string, perm: "can_read" | "can_write") {
    onChange(value.map((g) => (g.workspace_id === wsId ? { ...g, [perm]: !g[perm] } : g)));
  }

  if (workspaces.length === 0) {
    return <p className="text-sm text-slate-500">{t("grants.no_workspaces")}</p>;
  }

  return (
    <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-slate-200 p-2">
      {workspaces.map((ws) => {
        const grant = byId.get(ws.id);
        return (
          <div
            key={ws.id}
            className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-slate-50"
          >
            <div className="flex items-center gap-2">
              <Switch
                checked={grant !== undefined}
                onCheckedChange={(v) => toggleWorkspace(ws.id, v)}
                aria-label={t("grants.toggle_workspace", { name: ws.name })}
              />
              <span className="text-sm font-medium text-slate-700">{ws.name}</span>
            </div>
            {grant && (
              <div className="flex gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant={grant.can_read ? "default" : "outline"}
                  className="h-6 px-2 text-xs"
                  onClick={() => togglePerm(ws.id, "can_read")}
                  aria-pressed={grant.can_read}
                >
                  {t("grants.read")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={grant.can_write ? "default" : "outline"}
                  className="h-6 px-2 text-xs"
                  onClick={() => togglePerm(ws.id, "can_write")}
                  aria-pressed={grant.can_write}
                >
                  {t("grants.write")}
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
