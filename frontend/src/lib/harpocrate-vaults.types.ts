// 9 types miroirs des schemas Pydantic backend
// (cf. backend/src/rag/schemas/harpocrate_vaults.py)

export type VaultSummary = {
  id: string;
  name: string;
  label: string;
  base_url: string;
  api_key_id: string;
  probe_path: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type VaultCreateRequest = {
  name: string;
  label: string;
  base_url: string;
  api_key_id: string;
  api_key: string;
  probe_path?: string | null;
  is_default?: boolean;
};

export type VaultUpdateRequest = {
  label?: string;
  base_url?: string;
  probe_path?: string | null;
};

export type VaultRotateApiKeyRequest = {
  api_key_id: string;
  api_key: string;
};

export type VaultTestConnectionResult = {
  ok: boolean;
  detail: string;
  probe_path_used: string;
};

export type VaultRevealApiKeyResponse = {
  id: string;
  api_key_id: string;
  api_key: string;
};

export type WalletInfoResponse = {
  wallet_id: string;
  wallet_name: string | null;
  api_key_id: string;
  permissions: string[];
  api_key_expires_at: string | null;
};

export type SecretTypeSummary = {
  type_uuid: string;
  type: string;
  sous_type: string | null;
  label: string;
  deprecated: boolean;
};

export type SecretListItem = {
  id: string;
  name: string;
  description: string | null;
  is_placeholder: boolean;
  tags: string[];
};

export type SecretListResponse = {
  secrets: SecretListItem[];
  next_cursor: string | null;
};
