import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { WorkspacesList } from "@/pages/workspace/WorkspacesList";
import { WorkspacesEmptyState } from "@/pages/workspace/WorkspacesEmptyState";
import { WorkspaceDetailPanel } from "@/pages/workspace/WorkspaceDetailPanel";
import { CreateWorkspaceDialog } from "@/pages/workspace/CreateWorkspaceDialog";

export function WorkspacesPage() {
  const { data, isLoading } = useWorkspaces();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedName = searchParams.get("ws");
  const [createOpen, setCreateOpen] = useState(false);

  // Auto-sélection au premier load : premier workspace de la liste.
  useEffect(() => {
    if (isLoading) return;
    if (selectedName) return;
    if (!data || data.length === 0) return;
    const first = data[0];
    if (!first) return;
    setSearchParams({ ws: first.name }, { replace: true });
  }, [data, isLoading, selectedName, setSearchParams]);

  const handleSelect = (name: string) => {
    setSearchParams({ ws: name }, { replace: true });
  };

  const handleCreated = (ws: { name: string }) => {
    setSearchParams({ ws: ws.name }, { replace: true });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  const workspaces = data ?? [];

  // État vide : aucun workspace → plein écran empty state.
  if (workspaces.length === 0) {
    return (
      <>
        <div className="flex h-full">
          <WorkspacesEmptyState onCreate={() => setCreateOpen(true)} />
        </div>
        <CreateWorkspaceDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={handleCreated}
        />
      </>
    );
  }

  return (
    <>
      <div className="flex h-full">
        <WorkspacesList
          selectedName={selectedName}
          onSelect={handleSelect}
          onCreate={() => setCreateOpen(true)}
        />
        {selectedName && <WorkspaceDetailPanel name={selectedName} />}
      </div>
      <CreateWorkspaceDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />
    </>
  );
}
