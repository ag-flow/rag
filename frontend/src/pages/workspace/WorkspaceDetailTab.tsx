import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  onReveal: () => void;
  onRotate: () => void;
}

export function WorkspaceDetailTab(_props: Props) {
  return <div className="text-slate-500">Tab Détail (T5)</div>;
}
