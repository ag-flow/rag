"""Gate de charge serveur — enabler docflow 01f8992b.

Protège le serveur quand les jobs d'indexation le saturent : avant de picker
un job, le SyncWorker consulte `LoadGate.status()` — surchargé ⇒ il saute son
tour, les jobs attendent dans la file DB (backpressure naturel, aucun rejet,
aucune perte). Le trafic API n'est pas gaté (latence utilisateur, déjà protégé
par le throttling par endpoint).

Signaux (stdlib pur, décision architecte 2026-07-27) :
- **PSI CPU** (`/proc/pressure/cpu`, `some avg60`) : % du temps où des tâches
  ont ATTENDU le CPU sur la dernière minute — le vrai signal de saturation ;
- **mémoire cgroup v2** : working set (`memory.current - inactive_file`, le
  page cache récupérable exclu) rapporté à `memory.max` ; `memory.max=max`
  (illimité) ⇒ repli sur le meminfo de la MACHINE (1 - MemAvailable/MemTotal).

Racine `/proc` configurable (`RAG_LOAD_GATE_PROC_ROOT`) : dans un conteneur
Docker, `/proc` est un procfs neuf qui, sur une machine LXC, décrit le nœud
Proxmox entier (lxcfs ne s'y applique pas) — un faux 85 % a gelé l'indexation
du 20 au 24/09/2026. Le compose monte donc le `/proc` de la machine
(`/proc:/host/proc:ro`, bind récursif : montages lxcfs inclus).

Seuils pilotés par l'IHM via admin.env (relu à chaud) ; défauts prudents.
**Fail-open** : une métrique illisible vaut None et ne bloque jamais — le gate
protège, il ne doit pas pouvoir paralyser l'indexation sur un kernel sans PSI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from rag.admin_env import AdminEnvStore

log = structlog.get_logger(__name__)

MemorySource = Literal["cgroup", "meminfo"]


@dataclass(frozen=True)
class LoadGateStatus:
    enabled: bool
    overloaded: bool
    cpu_psi_avg60: float | None
    memory_used_pct: float | None
    # D'où vient le % mémoire : limite du conteneur ou meminfo de la machine.
    memory_source: MemorySource | None
    io_psi_avg60: float | None
    cpu_threshold_pct: int
    memory_threshold_pct: int
    io_threshold_pct: int
    reasons: list[str]


class LoadGate:
    """Lecture instantanée de la charge + verdict contre les seuils admin.env.

    `proc_root` désigne le `/proc` de la machine à protéger ; les chemins
    individuels restent injectables pour les tests. Fichiers minuscules →
    lectures synchrones acceptables dans le contexte asyncio."""

    def __init__(
        self,
        admin_env: AdminEnvStore,
        *,
        proc_root: Path = Path("/proc"),
        psi_cpu_path: Path | None = None,
        psi_io_path: Path | None = None,
        cgroup_dir: Path = Path("/sys/fs/cgroup"),
        meminfo_path: Path | None = None,
    ) -> None:
        self._admin_env = admin_env
        self._psi_cpu_path = psi_cpu_path or proc_root / "pressure" / "cpu"
        self._psi_io_path = psi_io_path or proc_root / "pressure" / "io"
        self._cgroup_dir = cgroup_dir
        self._meminfo_path = meminfo_path or proc_root / "meminfo"

    def _read_psi_avg60(self, path: Path) -> float | None:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
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

    def _read_inactive_file(self) -> int:
        """Page cache inactif du cgroup (récupérable) ; 0 si illisible — on
        retombe alors sur `memory.current` brut, jamais sur une sous-estimation."""
        try:
            for line in (self._cgroup_dir / "memory.stat").read_text().splitlines():
                key, _, value = line.partition(" ")
                if key == "inactive_file":
                    return int(value)
        except (OSError, ValueError):
            return 0
        return 0

    def _read_memory(self) -> tuple[float | None, MemorySource | None]:
        try:
            current = int((self._cgroup_dir / "memory.current").read_text().strip())
            raw_max = (self._cgroup_dir / "memory.max").read_text().strip()
            limit = None if raw_max == "max" else int(raw_max)
        except (OSError, ValueError):
            limit = None
        if limit is None:
            # Conteneur sans limite : la borne pertinente est la RAM de la machine.
            pct = self._read_meminfo_pct()
            return pct, ("meminfo" if pct is not None else None)
        if limit <= 0:
            return None, None
        working_set = max(0, current - self._read_inactive_file())
        return round(working_set / limit * 100, 1), "cgroup"

    def status(self) -> LoadGateStatus:
        enabled = self._admin_env.get_load_gate_enabled()
        cpu_threshold = self._admin_env.get_load_gate_cpu_psi_pct()
        memory_threshold = self._admin_env.get_load_gate_memory_pct()
        io_threshold = self._admin_env.get_load_gate_io_psi_pct()
        cpu = self._read_psi_avg60(self._psi_cpu_path)
        io_pressure = self._read_psi_avg60(self._psi_io_path)
        memory, memory_source = self._read_memory()
        reasons: list[str] = []
        if enabled:
            if cpu is not None and cpu > cpu_threshold:
                reasons.append(f"cpu psi avg60 {cpu} > {cpu_threshold}%")
            if memory is not None and memory > memory_threshold:
                reasons.append(f"memory {memory} > {memory_threshold}%")
            if io_pressure is not None and io_pressure > io_threshold:
                reasons.append(f"io psi avg60 {io_pressure} > {io_threshold}%")
        return LoadGateStatus(
            enabled=enabled,
            overloaded=bool(reasons),
            cpu_psi_avg60=cpu,
            memory_used_pct=memory,
            memory_source=memory_source,
            io_psi_avg60=io_pressure,
            cpu_threshold_pct=cpu_threshold,
            memory_threshold_pct=memory_threshold,
            io_threshold_pct=io_threshold,
            reasons=reasons,
        )
