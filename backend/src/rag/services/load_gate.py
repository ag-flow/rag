"""Gate de charge serveur — enabler docflow 01f8992b.

Protège le serveur quand les jobs d'indexation le saturent : avant de picker
un job, le SyncWorker consulte `LoadGate.status()` — surchargé ⇒ il saute son
tour, les jobs attendent dans la file DB (backpressure naturel, aucun rejet,
aucune perte). Le trafic API n'est pas gaté (latence utilisateur, déjà protégé
par le throttling par endpoint).

Signaux (stdlib pur, décision architecte 2026-07-27) :
- **PSI CPU** (`/proc/pressure/cpu`, `some avg60`) : % du temps où des tâches
  ont ATTENDU le CPU sur la dernière minute — le vrai signal de saturation ;
- **mémoire cgroup v2** (`memory.current`/`memory.max`) ; `memory.max=max`
  (illimité) ⇒ repli sur /proc/meminfo (1 - MemAvailable/MemTotal).

Seuils pilotés par l'IHM via admin.env (relu à chaud) ; défauts prudents.
**Fail-open** : une métrique illisible vaut None et ne bloque jamais — le gate
protège, il ne doit pas pouvoir paralyser l'indexation sur un kernel sans PSI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from rag.admin_env import AdminEnvStore

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class LoadGateStatus:
    enabled: bool
    overloaded: bool
    cpu_psi_avg60: float | None
    memory_used_pct: float | None
    cpu_threshold_pct: int
    memory_threshold_pct: int
    reasons: list[str]


class LoadGate:
    """Lecture instantanée de la charge + verdict contre les seuils admin.env.

    Chemins injectables pour les tests ; fichiers minuscules → lectures
    synchrones acceptables dans le contexte asyncio."""

    def __init__(
        self,
        admin_env: AdminEnvStore,
        *,
        psi_cpu_path: Path = Path("/proc/pressure/cpu"),
        cgroup_dir: Path = Path("/sys/fs/cgroup"),
        meminfo_path: Path = Path("/proc/meminfo"),
    ) -> None:
        self._admin_env = admin_env
        self._psi_cpu_path = psi_cpu_path
        self._cgroup_dir = cgroup_dir
        self._meminfo_path = meminfo_path

    def _read_psi_avg60(self) -> float | None:
        try:
            for line in self._psi_cpu_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("some"):
                    for token in line.split():
                        if token.startswith("avg60="):
                            return float(token.removeprefix("avg60="))
        except (OSError, ValueError):
            return None
        return None

    def _read_meminfo_pct(self) -> float | None:
        try:
            values: dict[str, int] = {}
            for line in self._meminfo_path.read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(rest.split()[0])
            total, available = values.get("MemTotal"), values.get("MemAvailable")
            if not total or available is None:
                return None
            return round((1 - available / total) * 100, 1)
        except (OSError, ValueError, IndexError):
            return None

    def _read_memory_pct(self) -> float | None:
        try:
            current = int((self._cgroup_dir / "memory.current").read_text().strip())
            raw_max = (self._cgroup_dir / "memory.max").read_text().strip()
        except (OSError, ValueError):
            return self._read_meminfo_pct()
        if raw_max == "max":
            # Cgroup sans limite : la borne pertinente est la RAM de l'hôte.
            return self._read_meminfo_pct()
        try:
            limit = int(raw_max)
        except ValueError:
            return self._read_meminfo_pct()
        if limit <= 0:
            return None
        return round(current / limit * 100, 1)

    def status(self) -> LoadGateStatus:
        enabled = self._admin_env.get_load_gate_enabled()
        cpu_threshold = self._admin_env.get_load_gate_cpu_psi_pct()
        memory_threshold = self._admin_env.get_load_gate_memory_pct()
        cpu = self._read_psi_avg60()
        memory = self._read_memory_pct()
        reasons: list[str] = []
        if enabled:
            if cpu is not None and cpu > cpu_threshold:
                reasons.append(f"cpu psi avg60 {cpu} > {cpu_threshold}%")
            if memory is not None and memory > memory_threshold:
                reasons.append(f"memory {memory} > {memory_threshold}%")
        return LoadGateStatus(
            enabled=enabled,
            overloaded=bool(reasons),
            cpu_psi_avg60=cpu,
            memory_used_pct=memory,
            cpu_threshold_pct=cpu_threshold,
            memory_threshold_pct=memory_threshold,
            reasons=reasons,
        )
