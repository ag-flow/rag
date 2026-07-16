// Types miroirs des schemas Pydantic user_api_keys
// (cf. backend/src/rag/schemas/user_api_keys.py)

export type WorkspaceGrant = {
  workspace_id: string;
  can_read: boolean;
  can_write: boolean;
};

export type WorkspaceGrantOut = WorkspaceGrant & {
  workspace_name: string;
};

export type UserApiKey = {
  id: string;
  name: string;
  fingerprint_preview: string;
  status: "active" | "grace_period" | "revoked" | "expired";
  created_at: string;
  revoked_at: string | null;
  rotated_at: string | null;
  workspaces: WorkspaceGrantOut[];
};

export type UserApiKeyCreate = {
  name: string;
  workspaces: WorkspaceGrant[];
};

export type UserApiKeyCreated = {
  id: string;
  name: string;
  api_key: string;
  fingerprint_preview: string;
  created_at: string;
};

export type UserApiKeyRotated = {
  new_key_id: string;
  new_api_key: string;
  new_fingerprint_preview: string;
  old_key_id: string;
  grace_until: string;
};
