import { api } from "./api";
import type { WebhookEnableResponse, WebhookRotateResponse } from "./source-webhooks.types";

const base = (workspace: string, source: string) =>
  `/api/admin/workspaces/${workspace}/sources/${source}/webhook`;

export const sourceWebhooksApi = {
  enable: (workspace: string, source: string): Promise<WebhookEnableResponse> =>
    api.post<WebhookEnableResponse>(`${base(workspace, source)}/enable`, {}),

  disable: (workspace: string, source: string): Promise<void> =>
    api.post<void>(`${base(workspace, source)}/disable`, {}),

  rotateSecret: (workspace: string, source: string): Promise<WebhookRotateResponse> =>
    api.post<WebhookRotateResponse>(`${base(workspace, source)}/rotate-secret`, {}),
};
