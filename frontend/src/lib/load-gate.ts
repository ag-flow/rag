import { api } from "@/lib/api";

// Gate de charge serveur (enabler 01f8992b) — miroir de rag/schemas/load_gate.py.
export type LoadGateStatus = {
  enabled: boolean;
  overloaded: boolean;
  cpu_psi_avg60: number | null;
  memory_used_pct: number | null;
  // Source de la mesure mémoire : limite du conteneur ou RAM de la machine.
  memory_source: "cgroup" | "meminfo" | null;
  io_psi_avg60: number | null;
  cpu_threshold_pct: number;
  memory_threshold_pct: number;
  io_threshold_pct: number;
  reasons: string[];
  // Début (ISO, UTC) de la pause effective du worker, null s'il picke.
  worker_paused_since: string | null;
};

export type LoadGateSettings = {
  enabled: boolean;
  cpu_threshold_pct: number;
  memory_threshold_pct: number;
  io_threshold_pct: number;
};

export const loadGateApi = {
  get: () => api.get<LoadGateStatus>("/api/admin/load-gate"),
  set: (settings: LoadGateSettings) => api.put<LoadGateStatus>("/api/admin/load-gate", settings),
};
