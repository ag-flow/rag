import { api } from "@/lib/api";

// Miroir des schemas Pydantic backend (GET/PUT /api/me/profile).
export type Profile = {
  username: string;
  email: string;
  /** GUID d'identité OBO (contrat v6) — null tant que non posé. */
  identity: string | null;
};

export type ProfileUpdate = {
  email?: string;
  /** undefined = inchangé ; "" = effacer ; sinon le GUID. */
  identity?: string;
};

export const profileApi = {
  get: () => api.get<Profile>("/api/me/profile"),
  update: (payload: ProfileUpdate) => api.put<Profile>("/api/me/profile", payload),
  generateIdentity: () =>
    api.post<{ identity: string }>("/api/me/profile/generate-identity", {}),
};
