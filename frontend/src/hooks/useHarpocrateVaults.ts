import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";
import type {
  GitCredentialCreate,
  GitCredentialUpdate,
  ProviderApiKeyCreate,
  ProviderApiKeyUpdate,
  SshKeyGenerate,
  SshKeyImport,
  VaultCreateRequest,
  VaultRotateApiKeyRequest,
  VaultTestConnectionResult,
  VaultUpdateRequest,
} from "@/lib/harpocrate-vaults.types";

const ROOT_KEY = ["vaults"] as const;

// ─── Queries ─────────────────────────────────────────

export function useVaults() {
  return useQuery({
    queryKey: ROOT_KEY,
    queryFn: harpocrateVaultsApi.list,
    staleTime: 30_000,
  });
}

export function useVault(id: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, id],
    queryFn: () => harpocrateVaultsApi.get(id as string),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useVaultWalletInfo(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: [...ROOT_KEY, id, "info"],
    queryFn: () => harpocrateVaultsApi.getWalletInfo(id as string),
    enabled: !!id && enabled,
    staleTime: 30_000,
  });
}

export function useVaultSecrets(
  id: string | null,
  filters: { path?: string; name_contains?: string; tag?: string; limit?: number },
  enabled: boolean,
) {
  return useQuery({
    queryKey: [...ROOT_KEY, id, "secrets", filters],
    queryFn: () => harpocrateVaultsApi.listSecrets(id as string, filters),
    enabled: !!id && enabled,
    staleTime: 30_000,
  });
}

// ─── Mutations ───────────────────────────────────────

export function useCreateVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultCreateRequest) => harpocrateVaultsApi.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ROOT_KEY });
    },
  });
}

export function useUpdateVault(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultUpdateRequest) => harpocrateVaultsApi.update(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ROOT_KEY });
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id] });
    },
  });
}

export function useDeleteVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => harpocrateVaultsApi.delete(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ROOT_KEY });
    },
  });
}

export function useReplaceApiKey(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultRotateApiKeyRequest) =>
      harpocrateVaultsApi.replaceApiKey(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id] });
      // Invalide aussi info wallet : api_key_id a peut-être changé.
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id, "info"] });
    },
  });
}

export function useSetDefaultVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => harpocrateVaultsApi.setDefault(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ROOT_KEY });
    },
  });
}

export function useTestConnection(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => harpocrateVaultsApi.testConnection(id),
    onSuccess: (result) => {
      // Stocke localement le dernier test pour le badge header (cf. useLastTestResult).
      qc.setQueryData([...ROOT_KEY, id, "lastTest"], result);
    },
  });
}

export function useLastTestResult(id: string | null): VaultTestConnectionResult | null {
  const qc = useQueryClient();
  if (!id) return null;
  return qc.getQueryData<VaultTestConnectionResult>([...ROOT_KEY, id, "lastTest"]) ?? null;
}

export function useRevealApiKey(id: string) {
  // Pas de cache : chaque appel = audit log côté backend (vault.reveal dans Loki).
  return useMutation({
    mutationFn: () => harpocrateVaultsApi.revealApiKey(id),
  });
}

export function useProviderKeys(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "provider-keys"],
    queryFn: () => harpocrateVaultsApi.listProviderKeys(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useCreateProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProviderApiKeyCreate) =>
      harpocrateVaultsApi.createProviderKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}

export function useUpdateProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: ProviderApiKeyUpdate }) =>
      harpocrateVaultsApi.updateProviderKey(vaultId, keyId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}

export function useDeleteProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      harpocrateVaultsApi.deleteProviderKey(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}

export function useGitCredentials(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "git-credentials"],
    queryFn: () => harpocrateVaultsApi.listGitCredentials(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useCreateGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: GitCredentialCreate) =>
      harpocrateVaultsApi.createGitCredential(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}

export function useUpdateGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: GitCredentialUpdate }) =>
      harpocrateVaultsApi.updateGitCredential(vaultId, keyId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}

export function useDeleteGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      harpocrateVaultsApi.deleteGitCredential(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}

export function useSshKeys(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "ssh-keys"],
    queryFn: () => harpocrateVaultsApi.listSshKeys(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useImportSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SshKeyImport) =>
      harpocrateVaultsApi.importSshKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}

export function useGenerateSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SshKeyGenerate) =>
      harpocrateVaultsApi.generateSshKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}

export function useDeleteSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => harpocrateVaultsApi.deleteSshKey(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}

export function useProviderKeysByProvider(provider: string | null) {
  return useQuery({
    queryKey: ["provider-keys-by-provider", provider],
    queryFn: () => harpocrateVaultsApi.listProviderKeysByProvider(provider!),
    enabled: !!provider,
    staleTime: 30_000,
  });
}

export function useGitCredentialsByHost(host: string | null) {
  return useQuery({
    queryKey: ["git-credentials-by-host", host],
    queryFn: () => harpocrateVaultsApi.listGitCredentialsByHost(host!),
    enabled: !!host,
    staleTime: 30_000,
  });
}

export function useSshKeysAll() {
  return useQuery({
    queryKey: ["ssh-keys-all"],
    queryFn: () => harpocrateVaultsApi.listSshKeysAll(),
    staleTime: 30_000,
  });
}
