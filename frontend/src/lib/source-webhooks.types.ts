export interface WebhookEnableResponse {
  source_name: string;
  webhook_url: string;
  secret: string;
}

export interface WebhookRotateResponse {
  secret: string;
}
