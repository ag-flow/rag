import { useQuery } from "@tanstack/react-query";

// Données publiques de l'écran de connexion (feature 2ca3ceb8) — aucun auth.

export type PublicStats = {
  indexed_documents: number | null;
  workspaces: number | null;
};

export type VersionInfo = {
  version: string;
  git: string;
  environment: string;
};

/** Compteurs du panneau de présentation. Fail-soft : en cas d'échec réseau,
 * les cellules restent vides (pas d'erreur bloquante sur la page de login). */
export function usePublicStats() {
  return useQuery<PublicStats | null>({
    queryKey: ["public", "stats"],
    queryFn: async () => {
      const r = await fetch("/api/public/stats");
      if (!r.ok) return null;
      return (await r.json()) as PublicStats;
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useVersionInfo() {
  return useQuery<VersionInfo | null>({
    queryKey: ["public", "version"],
    queryFn: async () => {
      const r = await fetch("/version");
      if (!r.ok) return null;
      return (await r.json()) as VersionInfo;
    },
    staleTime: Infinity,
    retry: false,
  });
}
