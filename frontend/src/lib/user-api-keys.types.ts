// Types miroirs des schemas Pydantic user_api_keys
// (cf. backend/src/rag/schemas/user_api_keys.py)

/** Niveau d'accès d'une clé API (unique, cross-workspaces). */
export type KeyScope = "read" | "read_write" | "admin";

export type UserApiKey = {
  id: string;
  name: string;
  fingerprint_preview: string;
  status: "active" | "grace_period" | "revoked" | "expired";
  created_at: string;
  revoked_at: string | null;
  rotated_at: string | null;
  scope: KeyScope;
};

export type UserApiKeyCreate = {
  name: string;
  scope: KeyScope;
};

export type UserApiKeyCreated = {
  id: string;
  name: string;
  api_key: string;
  fingerprint_preview: string;
  scope: KeyScope;
  created_at: string;
};

export type UserApiKeyRotated = {
  new_key_id: string;
  new_api_key: string;
  new_fingerprint_preview: string;
  old_key_id: string;
  grace_until: string;
};
