import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { WorkspacesList } from "@/pages/workspace/WorkspacesList";
import { WorkspacesEmptyState } from "@/pages/workspace/WorkspacesEmptyState";
import { WorkspaceDetailPanel } from "@/pages/workspace/WorkspaceDetailPanel";
import { CreateWorkspaceDialog } from "@/pages/workspace/CreateWorkspaceDialog";

export function WorkspacesPage() {
  const { data, isLoading, isFetching } = useWorkspaces();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedName = searchParams.get("ws");
  const [createOpen, setCreateOpen] = useState(false);

  // Auto-sélection au premier load : premier workspace de la liste.
  // On attend que le refetch de la liste soit stabilisé (isFetching=false)
  // avant d'auto-sélectionner, pour ne pas re-sélectionner un workspace
  // tout juste supprimé depuis des données de cache périmées.
  useEffect(() => {
    if (isLoading || isFetching) return;
    if (selectedName) return;
    if (!data || data.length === 0) return;
    const first = data[0];
    if (!first) return;
    setSearchParams({ ws: first.name }, { replace: true });
  }, [data, isLoading, isFetching, selectedName, setSearchParams]);

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
