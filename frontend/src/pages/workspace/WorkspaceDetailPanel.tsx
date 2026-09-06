import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useWorkspace } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceDetailTab } from "./WorkspaceDetailTab";
import { WorkspaceSourcesTab } from "./WorkspaceSourcesTab";
import { WorkspaceJobsTab } from "./WorkspaceJobsTab";
import { WorkspaceChunkingTab } from "./WorkspaceChunkingTab";
import { WorkspaceSearchTab } from "./WorkspaceSearchTab";
import { WorkspaceWebhooksTab } from "./WorkspaceWebhooksTab";
import { WorkspacePlaygroundTab } from "./WorkspacePlaygroundTab";
import { WorkspaceTriggersTab } from "./WorkspaceTriggersTab";
import { WorkspaceIndexTab } from "./WorkspaceIndexTab";
import { WorkspaceSearchTestTab } from "./WorkspaceSearchTestTab";
import { ReindexConfirmDialog } from "./ReindexConfirmDialog";
import { DeleteWorkspaceAlert } from "./DeleteWorkspaceAlert";

interface Props {
  name: string;
}

type DialogKey = "reindex" | "delete" | null;

export function WorkspaceDetailPanel({ name }: Props) {
  const { t } = useTranslation("workspace");
  const { data: ws, isLoading, isError } = useWorkspace(name);
  // Liens profonds (ex. Push activity → onglet Index sur un document) :
  // ?tab=<onglet> ouvre l'onglet, ?doc=<path> est transmis à l'onglet Index.
  const [searchParams] = useSearchParams();
  const urlTab = searchParams.get("tab");
  const focusDoc = searchParams.get("doc");
  const [activeTab, setActiveTab] = useState(urlTab ?? "detail");
  const [openDialog, setOpenDialog] = useState<DialogKey>(null);
  useEffect(() => {
    if (urlTab) setActiveTab(urlTab);
  }, [urlTab, focusDoc]);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !ws) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-rose-600">
        {t("panel.load_error")}
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 overflow-auto">
      <WorkspaceHeader
        workspace={ws}
        onReindex={() => setOpenDialog("reindex")}
        onDelete={() => setOpenDialog("delete")}
      />
      <Tabs value={activeTab} onValueChange={setActiveTab} className="px-6 py-4">
        <TabsList>
          <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
          <TabsTrigger value="chunking">{t("tabs.chunking")}</TabsTrigger>
          <TabsTrigger value="triggers">{t("tabs.triggers")}</TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
          <TabsTrigger value="index">{t("tabs.index")}</TabsTrigger>
          <TabsTrigger value="sources">
            {t("tabs.sources", { count: ws.sources_count })}
          </TabsTrigger>
          <TabsTrigger value="search">{t("tabs.search")}</TabsTrigger>
          <TabsTrigger value="search-test">{t("tabs.search_test")}</TabsTrigger>
          <TabsTrigger value="webhooks">{t("webhooks.tab")}</TabsTrigger>
          <TabsTrigger value="playground">{t("tabs.playground")}</TabsTrigger>
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
        <TabsContent value="index" className="pt-4">
          <WorkspaceIndexTab
            workspaceName={ws.name}
            enabled={activeTab === "index"}
            focusPath={focusDoc}
          />
        </TabsContent>
        <TabsContent value="chunking" className="pt-4">
          <WorkspaceChunkingTab workspace={ws} enabled={activeTab === "chunking"} />
        </TabsContent>
        <TabsContent value="search" className="pt-4">
          <WorkspaceSearchTab name={ws.name} enabled={activeTab === "search"} />
        </TabsContent>
        <TabsContent value="search-test" className="pt-4">
          <WorkspaceSearchTestTab workspaceName={ws.name} enabled={activeTab === "search-test"} />
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
