import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceDetailTab } from "./WorkspaceDetailTab";
import { WorkspaceSourcesTab } from "./WorkspaceSourcesTab";
import { WorkspaceJobsTab } from "./WorkspaceJobsTab";
import { WorkspaceModelTab } from "./WorkspaceModelTab";
import { WorkspaceRerankTab } from "./WorkspaceRerankTab";
import { WorkspaceChunkingTab } from "./WorkspaceChunkingTab";
import { RevealApiKeyDialog } from "./RevealApiKeyDialog";
import { RotateApiKeyDialog } from "./RotateApiKeyDialog";
import { ReindexConfirmDialog } from "./ReindexConfirmDialog";
import { DeleteWorkspaceAlert } from "./DeleteWorkspaceAlert";

interface Props {
  name: string;
}

type DialogKey = "reveal" | "rotate" | "reindex" | "delete" | null;

export function WorkspaceDetailPanel({ name }: Props) {
  const { t } = useTranslation("workspace");
  const { data: ws, isLoading } = useWorkspace(name);
  const [activeTab, setActiveTab] = useState("detail");
  const [openDialog, setOpenDialog] = useState<DialogKey>(null);

  if (isLoading || !ws) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="flex-1 max-w-[760px] overflow-auto">
      <WorkspaceHeader
        workspace={ws}
        onReindex={() => setOpenDialog("reindex")}
        onReveal={() => setOpenDialog("reveal")}
        onRotate={() => setOpenDialog("rotate")}
        onDelete={() => setOpenDialog("delete")}
      />
      <Tabs value={activeTab} onValueChange={setActiveTab} className="px-6 py-4">
        <TabsList>
          <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
          <TabsTrigger value="sources">
            {t("tabs.sources", { count: ws.sources_count })}
          </TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
          <TabsTrigger value="model">{t("tabs.model")}</TabsTrigger>
          <TabsTrigger value="rerank">{t("tabs.rerank")}</TabsTrigger>
          <TabsTrigger value="chunking">{t("tabs.chunking")}</TabsTrigger>
        </TabsList>
        <TabsContent value="detail" className="pt-4">
          <WorkspaceDetailTab
            workspace={ws}
            onReveal={() => setOpenDialog("reveal")}
            onRotate={() => setOpenDialog("rotate")}
          />
        </TabsContent>
        <TabsContent value="sources" className="pt-4">
          <WorkspaceSourcesTab name={ws.name} enabled={activeTab === "sources"} />
        </TabsContent>
        <TabsContent value="jobs" className="pt-4">
          <WorkspaceJobsTab name={ws.name} enabled={activeTab === "jobs"} />
        </TabsContent>
        <TabsContent value="model" className="pt-4">
          <WorkspaceModelTab workspace={ws} />
        </TabsContent>
        <TabsContent value="rerank" className="pt-4">
          <WorkspaceRerankTab workspace={ws} enabled={activeTab === "rerank"} />
        </TabsContent>
        <TabsContent value="chunking" className="pt-4">
          <WorkspaceChunkingTab workspace={ws} enabled={activeTab === "chunking"} />
        </TabsContent>
      </Tabs>
      <RevealApiKeyDialog
        name={ws.name}
        open={openDialog === "reveal"}
        onOpenChange={(o) => !o && setOpenDialog(null)}
      />
      <RotateApiKeyDialog
        name={ws.name}
        open={openDialog === "rotate"}
        onOpenChange={(o) => !o && setOpenDialog(null)}
      />
      <ReindexConfirmDialog
        name={ws.name}
        open={openDialog === "reindex"}
        onOpenChange={(o) => !o && setOpenDialog(null)}
      />
      <DeleteWorkspaceAlert
        name={ws.name}
        open={openDialog === "delete"}
        onOpenChange={(o) => !o && setOpenDialog(null)}
      />
    </div>
  );
}
