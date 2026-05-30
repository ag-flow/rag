import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceDetailTab } from "./WorkspaceDetailTab";
import { WorkspaceSourcesTab } from "./WorkspaceSourcesTab";
import { WorkspaceJobsTab } from "./WorkspaceJobsTab";
import { WorkspaceChunkingTab } from "./WorkspaceChunkingTab";
import { WorkspaceWebhooksTab } from "./WorkspaceWebhooksTab";
import { WorkspacePlaygroundTab } from "./WorkspacePlaygroundTab";
import { WorkspaceTriggersTab } from "./WorkspaceTriggersTab";
import { WorkspaceApiKeysTab } from "./WorkspaceApiKeysTab";
import { ReindexConfirmDialog } from "./ReindexConfirmDialog";
import { DeleteWorkspaceAlert } from "./DeleteWorkspaceAlert";

interface Props {
  name: string;
}

type DialogKey = "reindex" | "delete" | null;

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
        onDelete={() => setOpenDialog("delete")}
      />
      <Tabs value={activeTab} onValueChange={setActiveTab} className="px-6 py-4">
        <TabsList>
          <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
          <TabsTrigger value="sources">
            {t("tabs.sources", { count: ws.sources_count })}
          </TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
          <TabsTrigger value="chunking">{t("tabs.chunking")}</TabsTrigger>
          <TabsTrigger value="webhooks">{t("webhooks.tab")}</TabsTrigger>
          <TabsTrigger value="playground">{t("tabs.playground")}</TabsTrigger>
          <TabsTrigger value="triggers">{t("tabs.triggers")}</TabsTrigger>
          <TabsTrigger value="apikeys">{t("tabs.apikeys")}</TabsTrigger>
        </TabsList>
        <TabsContent value="detail" className="pt-4">
          <WorkspaceDetailTab workspace={ws} enabled={activeTab === "detail"} />
        </TabsContent>
        <TabsContent value="sources" className="pt-4">
          <WorkspaceSourcesTab name={ws.name} enabled={activeTab === "sources"} />
        </TabsContent>
        <TabsContent value="jobs" className="pt-4">
          <WorkspaceJobsTab name={ws.name} enabled={activeTab === "jobs"} />
        </TabsContent>
        <TabsContent value="chunking" className="pt-4">
          <WorkspaceChunkingTab workspace={ws} enabled={activeTab === "chunking"} />
        </TabsContent>
        <TabsContent value="webhooks" className="pt-4">
          <WorkspaceWebhooksTab workspaceName={ws.name} />
        </TabsContent>
        <TabsContent value="playground" className="pt-4">
          <WorkspacePlaygroundTab workspaceName={ws.name} />
        </TabsContent>
        <TabsContent value="triggers" className="pt-4">
          <WorkspaceTriggersTab workspaceName={ws.name} />
        </TabsContent>
        <TabsContent value="apikeys" className="pt-4">
          <WorkspaceApiKeysTab workspaceName={ws.name} />
        </TabsContent>
      </Tabs>
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
