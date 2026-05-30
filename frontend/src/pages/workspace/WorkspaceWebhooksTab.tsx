import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  createWebhook,
  deleteWebhook,
  listWebhooks,
  patchWebhook,
} from "@/lib/webhooks";
import type { Webhook, WebhookCreatePayload } from "@/lib/webhooks.types";
import { WebhookForm } from "./WebhookForm";
import { WebhookCallsLog } from "./WebhookCallsLog";

interface Props {
  workspaceName: string;
}

export function WorkspaceWebhooksTab({ workspaceName }: Props) {
  const { t } = useTranslation("workspace");
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [subTab, setSubTab] = useState("list");

  const { data: webhooks = [] } = useQuery({
    queryKey: ["webhooks", workspaceName],
    queryFn: () => listWebhooks(workspaceName),
  });

  const createMutation = useMutation({
    mutationFn: (payload: WebhookCreatePayload) =>
      createWebhook(workspaceName, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] });
      setShowForm(false);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      patchWebhook(workspaceName, id, { enabled }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWebhook(workspaceName, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] }),
  });

  return (
    <Tabs value={subTab} onValueChange={setSubTab}>
      <div className="flex items-center justify-between mb-4">
        <TabsList>
          <TabsTrigger value="list">{t("webhooks.list_title")}</TabsTrigger>
          <TabsTrigger value="calls">{t("webhooks.calls_title")}</TabsTrigger>
        </TabsList>
        {subTab === "list" && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            {t("webhooks.add")}
          </Button>
        )}
      </div>

      <TabsContent value="list">
        {webhooks.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("webhooks.empty")}
          </p>
        ) : (
          <div className="space-y-2">
            {webhooks.map((wh: Webhook) => (
              <div
                key={wh.id}
                className="flex items-center justify-between border rounded p-3"
              >
                <div>
                  <span className="font-medium">{wh.name}</span>
                  <span className="text-xs text-muted-foreground ml-2 truncate max-w-[200px] inline-block align-bottom">
                    {wh.url}
                  </span>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {t("webhooks.headers_count_one", {
                      count: wh.headers.length,
                    })}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      toggleMutation.mutate({
                        id: wh.id,
                        enabled: !wh.enabled,
                      })
                    }
                  >
                    <Badge
                      variant={wh.enabled ? "default" : "secondary"}
                    >
                      {wh.enabled
                        ? t("webhooks.enabled")
                        : t("webhooks.disabled")}
                    </Badge>
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm">
                        &times;
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {t("webhooks.delete_confirm")}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("webhooks.delete_confirm_description")}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          {t("webhooks.cancel")}
                        </AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate(wh.id)}
                        >
                          {t("webhooks.delete_confirm")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="calls">
        <WebhookCallsLog workspaceName={workspaceName} />
      </TabsContent>

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("webhooks.form_title_create")}</DialogTitle>
          </DialogHeader>
          <WebhookForm
            onSubmit={(p) => createMutation.mutate(p)}
            onCancel={() => setShowForm(false)}
            loading={createMutation.isPending}
          />
        </DialogContent>
      </Dialog>
    </Tabs>
  );
}
