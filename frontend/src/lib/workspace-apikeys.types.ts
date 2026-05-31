export type ApiKeyStatus = "active" | "grace_period" | "revoked" | "expired";

export type ApiKey = {
  id: string;
  name: string;
  fingerprint_preview: string;
  api_key_ref: string;
  status: ApiKeyStatus;
  created_at: string;
  revoked_at: string | null;
  rotated_at: string | null;
};

export type ApiKeyCreate = {
  name: string;
};

export type ApiKeyCreated = {
  id: string;
  name: string;
  fingerprint_preview: string;
  api_key: string;
  created_at: string;
};

export type ApiKeyRotated = {
  new_key_id: string;
  new_api_key: string;
  new_fingerprint_preview: string;
  old_key_id: string;
  grace_until: string;
};
