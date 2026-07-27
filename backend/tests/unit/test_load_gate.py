"""Gate de charge serveur (enabler 01f8992b) : PSI CPU + mémoire cgroup v2,
seuils pilotés par l'IHM (admin.env, relu à chaud), fail-open si les fichiers
de métriques sont absents."""

from __future__ import annotations

from pathlib import Path

from rag.admin_env import AdminEnvStore
from rag.services.load_gate import LoadGate

_PSI = (
    "some avg10=0.66 avg60={avg60} avg300=0.50 total=20814601692\n"
    "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
)


def _gate(
    tmp_path: Path,
    *,
    psi_avg60: float | None = 5.0,
    mem_current: int | None = 2 * 1024**3,
    mem_max: str | None = str(8 * 1024**3),
    env_lines: str = "",
) -> LoadGate:
    admin_env = AdminEnvStore(tmp_path / "admin.env")
    if env_lines:
        (tmp_path / "admin.env").write_text(env_lines, encoding="utf-8")
    psi = tmp_path / "pressure_cpu"
    if psi_avg60 is not None:
        psi.write_text(_PSI.format(avg60=psi_avg60), encoding="utf-8")
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir(exist_ok=True)
    if mem_current is not None:
        (cgroup / "memory.current").write_text(f"{mem_current}\n", encoding="utf-8")
    if mem_max is not None:
        (cgroup / "memory.max").write_text(f"{mem_max}\n", encoding="utf-8")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       16000000 kB\nMemFree:         2000000 kB\nMemAvailable:    8000000 kB\n",
        encoding="utf-8",
    )
    return LoadGate(admin_env, psi_cpu_path=psi, cgroup_dir=cgroup, meminfo_path=meminfo)


class TestMetrics:
    def test_reads_psi_avg60_and_memory_pct(self, tmp_path: Path) -> None:
        st = _gate(tmp_path, psi_avg60=12.5).status()
        assert st.cpu_psi_avg60 == 12.5
        assert st.memory_used_pct == 25.0
        assert st.overloaded is False

    def test_memory_max_unlimited_falls_back_to_meminfo(self, tmp_path: Path) -> None:
        # memory.max = "max" ⇒ % dérivé de /proc/meminfo (1 - available/total).
        st = _gate(tmp_path, mem_max="max").status()
        assert st.memory_used_pct == 50.0

    def test_missing_metric_files_fail_open(self, tmp_path: Path) -> None:
        gate = _gate(tmp_path, psi_avg60=None, mem_current=None, mem_max=None)
        # meminfo reste lisible → mémoire connue ; PSI absent → None, pas de blocage.
        st = gate.status()
        assert st.cpu_psi_avg60 is None
        assert st.overloaded is False


class TestThresholds:
    def test_cpu_pressure_above_threshold_overloads(self, tmp_path: Path) -> None:
        st = _gate(tmp_path, psi_avg60=55.0).status()
        assert st.overloaded is True
        assert any("cpu" in r for r in st.reasons)

    def test_memory_above_threshold_overloads(self, tmp_path: Path) -> None:
        st = _gate(tmp_path, mem_current=7 * 1024**3).status()  # 87.5 % de 8 Gio
        assert st.overloaded is True
        assert any("memory" in r for r in st.reasons)

    def test_custom_thresholds_from_admin_env(self, tmp_path: Path) -> None:
        st = _gate(
            tmp_path,
            psi_avg60=15.0,
            env_lines="RAG_LOAD_GATE_CPU_PSI_PCT=10\n",
        ).status()
        assert st.cpu_threshold_pct == 10
        assert st.overloaded is True

    def test_disabled_never_overloads(self, tmp_path: Path) -> None:
        st = _gate(
            tmp_path,
            psi_avg60=99.0,
            env_lines="RAG_LOAD_GATE_ENABLED=false\n",
        ).status()
        assert st.enabled is False
        assert st.overloaded is False
