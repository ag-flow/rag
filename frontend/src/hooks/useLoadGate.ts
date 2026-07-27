import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { loadGateApi } from "@/lib/load-gate";
import type { LoadGateSettings, LoadGateStatus } from "@/lib/load-gate";

const LOAD_GATE_KEY = ["load-gate"];

export function useLoadGate() {
  return useQuery<LoadGateStatus>({
    queryKey: LOAD_GATE_KEY,
    queryFn: () => loadGateApi.get(),
    // Métriques instantanées : on rafraîchit tant que la page est visible.
    refetchInterval: 10_000,
  });
}

export function useSetLoadGate() {
  const qc = useQueryClient();
  return useMutation<LoadGateStatus, Error, LoadGateSettings>({
    mutationFn: (settings) => loadGateApi.set(settings),
    onSuccess: (status) => qc.setQueryData(LOAD_GATE_KEY, status),
  });
}
