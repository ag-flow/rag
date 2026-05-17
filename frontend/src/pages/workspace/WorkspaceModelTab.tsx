import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
}

export function WorkspaceModelTab(_props: Props) {
  return <div className="text-slate-500">Tab Modèle (T8)</div>;
}
