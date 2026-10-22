import { api } from "@/lib/api";

/** Rôle d'un compte en base ; null = accès retiré (le compte et ses objets restent). */
export type UserRole = "rag-admin" | "rag-viewer" | null;

export type UserAccount = {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  /** Émetteur OIDC du compte ancré ; null = jamais connecté en OIDC. */
  oidc_issuer: string | null;
  has_local_password: boolean;
  created_at: string;
};

const BASE = "/api/admin/users";

export const usersApi = {
  list: () => api.get<UserAccount[]>(BASE),
  setRole: (userId: string, role: UserRole) =>
    api.patch<UserAccount>(`${BASE}/${userId}/role`, { role }),
};
