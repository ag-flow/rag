import { api } from "@/lib/api";
import type {
  Webhook,
  WebhookCall,
  WebhookCallsFilter,
  WebhookCreatePayload,
  WebhookPatchPayload,
} from "@/lib/webhooks.types";

const base = (workspace: string) =>
  `/api/admin/workspaces/${workspace}/webhooks`;

export async function listWebhooks(workspace: string): Promise<Webhook[]> {
  return api.get<Webhook[]>(base(workspace));
}

export async function createWebhook(
  workspace: string,
  payload: WebhookCreatePayload,
): Promise<Webhook> {
  return api.post<Webhook>(base(workspace), payload);
}

export async function patchWebhook(
  workspace: string,
  webhookId: string,
  payload: WebhookPatchPayload,
): Promise<Webhook> {
  return api.patch<Webhook>(`${base(workspace)}/${webhookId}`, payload);
}

export async function deleteWebhook(
  workspace: string,
  webhookId: string,
): Promise<void> {
  return api.delete<void>(`${base(workspace)}/${webhookId}`);
}

export async function listWebhookCalls(
  workspace: string,
  filter: WebhookCallsFilter = {},
): Promise<WebhookCall[]> {
  const params = new URLSearchParams();
  if (filter.webhook_id) params.set("webhook_id", filter.webhook_id);
  if (filter.correlation_id)
    params.set("correlation_id", filter.correlation_id);
  if (filter.status) params.set("status", filter.status);
  if (filter.limit) params.set("limit", String(filter.limit));
  const query = params.toString();
  return api.get<WebhookCall[]>(
    `${base(workspace)}/calls${query ? `?${query}` : ""}`,
  );
}

export async function purgeWebhookCalls(workspace: string): Promise<void> {
  return api.delete<void>(`${base(workspace)}/calls`);
}
