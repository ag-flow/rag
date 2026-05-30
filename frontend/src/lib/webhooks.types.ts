export interface WebhookHeader {
  id: string;
  name: string;
  value: null;
  vault_ref: string | null;
  enabled: boolean;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  headers: WebhookHeader[];
}

export interface WebhookHeaderIn {
  name: string;
  value: string | null;
  vault: string | null;
  enabled: boolean;
}

export interface WebhookCreatePayload {
  name: string;
  url: string;
  enabled: boolean;
  headers: WebhookHeaderIn[];
}

export interface WebhookPatchPayload {
  name?: string;
  url?: string;
  enabled?: boolean;
}

export interface WebhookCall {
  id: string;
  webhook_id: string;
  webhook_name: string;
  correlation_id: string;
  triggered_by: string;
  webhook_url: string;
  http_status: number | null;
  error: string | null;
  duration_ms: number | null;
  called_at: string;
  success: boolean;
}

export interface WebhookCallsFilter {
  webhook_id?: string;
  correlation_id?: string;
  status?: "success" | "error";
  limit?: number;
}
