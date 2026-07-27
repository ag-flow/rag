import { api } from "@/lib/api";

// Gate de charge serveur (enabler 01f8992b) — miroir de rag/schemas/load_gate.py.
export type LoadGateStatus = {
  enabled: boolean;
  overloaded: boolean;
  cpu_psi_avg60: number | null;
  memory_used_pct: number | null;
  cpu_threshold_pct: number;
  memory_threshold_pct: number;
  reasons: string[];
};

export type LoadGateSettings = {
  enabled: boolean;
  cpu_threshold_pct: number;
  memory_threshold_pct: number;
};

export const loadGateApi = {
  get: () => api.get<LoadGateStatus>("/api/admin/load-gate"),
  set: (settings: LoadGateSettings) => api.put<LoadGateStatus>("/api/admin/load-gate", settings),
};
