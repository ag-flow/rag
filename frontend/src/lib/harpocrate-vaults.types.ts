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

export type ProviderApiKey = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  expires_at: string | null;
  created_at: string;
};

export type ProviderApiKeyCreate = {
  key_id: string;
  label: string;
  provider: string;
  value: string;
  valid_days?: number | null;
};

export type ProviderApiKeyUpdate = {
  label?: string;
  value?: string;
  valid_days?: number | null;
};

export type GitHost =
  | "github"
  | "gitlab"
  | "gitea"
  | "bitbucket"
  | "azure-devops";

export type GitCredential = {
  id: string;
  key_id: string;
  label: string;
  host: GitHost;
  scope_url: string | null;
  harpo_path: string;
  expires_at: string | null;
  created_at: string;
};

export type GitCredentialCreate = {
  key_id: string;
  label: string;
  host: GitHost;
  scope_url?: string | null;
  value: string;
  valid_days?: number | null;
};

export type GitCredentialUpdate = {
  label?: string;
  scope_url?: string | null;
  value?: string;
  valid_days?: number | null;
};

export type SshKeyType = "ed25519" | "rsa-4096" | "ecdsa-256";

export type SshKey = {
  id: string;
  key_id: string;
  name: string;
  key_type: string;
  public_key: string;
  passphrase_protected: boolean;
  harpo_path: string;
  created_at: string;
};

export type SshKeyImport = {
  key_id: string;
  name: string;
  private_key: string;
  public_key: string;
  passphrase?: string | null;
};

export type SshKeyGenerate = {
  key_id: string;
  name: string;
  key_type: SshKeyType;
};

export type ProviderApiKeyWithVault = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};
