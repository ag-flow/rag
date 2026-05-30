import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listWebhookCalls, purgeWebhookCalls } from "@/lib/webhooks";
import type { WebhookCallsFilter } from "@/lib/webhooks.types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface Props {
  workspaceName: string;
}

export function WebhookCallsLog({ workspaceName }: Props) {
  const { t } = useTranslation("workspace");
  const qc = useQueryClient();
  const [filter, setFilter] = useState<WebhookCallsFilter>({});

  const { data: calls = [] } = useQuery({
    queryKey: ["webhook-calls", workspaceName, filter],
    queryFn: () => listWebhookCalls(workspaceName, filter),
    refetchInterval: 30_000,
  });

  const purgeMutation = useMutation({
    mutationFn: () => purgeWebhookCalls(workspaceName),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["webhook-calls", workspaceName] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap items-center">
        <Input
          placeholder={t("webhooks.filter_correlation")}
          className="w-48"
          onChange={(e) => {
            const val = e.target.value;
            setFilter((f) => {
              const next = { ...f };
              if (val) {
                next.correlation_id = val;
              } else {
                delete next.correlation_id;
              }
              return next;
            });
          }}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          onChange={(e) => {
            const val = e.target.value as WebhookCallsFilter["status"] | "";
            setFilter((f) => {
              const next = { ...f };
              if (val) {
                next.status = val;
              } else {
                delete next.status;
              }
              return next;
            });
          }}
        >
          <option value="">{t("webhooks.filter_all")}</option>
          <option value="success">{t("webhooks.filter_success")}</option>
          <option value="error">{t("webhooks.filter_error")}</option>
        </select>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => purgeMutation.mutate()}
          disabled={purgeMutation.isPending}
        >
          {t("webhooks.purge")}
        </Button>
      </div>

      {calls.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("webhooks.calls_empty")}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("webhooks.col_date")}</TableHead>
              <TableHead>{t("webhooks.col_webhook")}</TableHead>
              <TableHead>{t("webhooks.col_status")}</TableHead>
              <TableHead>{t("webhooks.col_duration")}</TableHead>
              <TableHead>{t("webhooks.col_correlation")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {calls.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="text-xs">
                  {new Date(c.called_at).toLocaleTimeString()}
                </TableCell>
                <TableCell>{c.webhook_name}</TableCell>
                <TableCell>
                  {c.http_status != null ? (
                    <Badge variant={c.success ? "default" : "destructive"}>
                      {c.http_status}
                    </Badge>
                  ) : (
                    <Badge variant="destructive">ERR</Badge>
                  )}
                </TableCell>
                <TableCell>
                  {c.duration_ms != null ? `${c.duration_ms}ms` : "—"}
                </TableCell>
                <TableCell className="font-mono text-xs truncate max-w-[120px]">
                  {c.correlation_id}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
