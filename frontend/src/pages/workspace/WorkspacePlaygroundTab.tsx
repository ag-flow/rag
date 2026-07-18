import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PlaygroundLlmConfigTab } from "./PlaygroundLlmConfigTab";
import { PlaygroundChatTab } from "./PlaygroundChatTab";
import { PlaygroundChunkPreviewTab } from "./PlaygroundChunkPreviewTab";
import { PlaygroundSearchTab } from "./PlaygroundSearchTab";

interface Props {
  workspaceName: string;
}

export function WorkspacePlaygroundTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const [sub, setSub] = useState("chat");

  return (
    <Tabs value={sub} onValueChange={setSub}>
      <TabsList>
        <TabsTrigger value="chat">{t("tabs.chat")}</TabsTrigger>
        <TabsTrigger value="config">{t("tabs.config")}</TabsTrigger>
        <TabsTrigger value="chunk-preview">{t("tabs.chunkPreview")}</TabsTrigger>
        <TabsTrigger value="search">{t("tabs.search")}</TabsTrigger>
      </TabsList>
      <TabsContent value="chat" className="pt-4">
        <PlaygroundChatTab workspaceName={workspaceName} />
      </TabsContent>
      <TabsContent value="config" className="pt-4">
        <PlaygroundLlmConfigTab workspaceName={workspaceName} />
      </TabsContent>
      <TabsContent value="chunk-preview" className="pt-4">
        <PlaygroundChunkPreviewTab workspaceName={workspaceName} />
      </TabsContent>
      <TabsContent value="search" className="pt-4">
        <PlaygroundSearchTab workspaceName={workspaceName} />
      </TabsContent>
    </Tabs>
  );
}
