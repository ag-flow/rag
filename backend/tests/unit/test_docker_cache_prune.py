"""scripts/docker-cache-prune.sh : purge bornée du cache Docker (ticket cef4eff3).

Le vrai binaire docker est remplacé par une doublure placée en tête du PATH,
qui journalise ses arguments et échoue sur demande.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "docker-cache-prune.sh"

_FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$DOCKER_CALLS"
if [ -n "${DOCKER_FAIL:-}" ] && [[ "$*" == *"$DOCKER_FAIL"* ]]; then
  echo "Error: daemon unreachable" >&2
  exit 1
fi
case "$1" in
  builder) echo "ID x"; echo "Total:  1.2GB" ;;
  image) echo "Deleted: sha256:abc"; echo "Total reclaimed space: 300MB" ;;
esac
"""


def _run(
    tmp_path: Path, stamp: Path, *args: str, fail: str = ""
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(_FAKE_DOCKER)
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_CALLS": str(tmp_path / "calls.log"),
        "DOCKER_FAIL": fail,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), str(stamp), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_prune_without_stamp_purges_cache_and_dangling_then_writes_stamp(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp"
    result = _run(tmp_path, stamp)
    assert result.returncode == 0
    assert _calls(tmp_path) == ["builder prune -a -f", "image prune -f"]
    assert "Total:  1.2GB" in result.stdout
    assert "Total reclaimed space: 300MB" in result.stdout
    assert stamp.exists()


def test_prune_with_recent_stamp_skips_docker(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp"
    stamp.touch()
    result = _run(tmp_path, stamp)
    assert result.returncode == 0
    assert _calls(tmp_path) == []
    assert "sautée" in result.stdout


def test_prune_with_stamp_older_than_interval_purges_again(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp"
    stamp.touch()
    eight_days_ago = time.time() - 8 * 86400
    os.utime(stamp, (eight_days_ago, eight_days_ago))
    result = _run(tmp_path, stamp)
    assert result.returncode == 0
    assert len(_calls(tmp_path)) == 2
    assert stamp.stat().st_mtime > eight_days_ago + 86400


def test_prune_docker_failure_exits_zero_and_keeps_stamp_unwritten(tmp_path: Path) -> None:
    """Une purge ratée ne fait jamais échouer le déploiement, et sera retentée."""
    stamp = tmp_path / "stamp"
    result = _run(tmp_path, stamp, fail="builder")
    assert result.returncode == 0
    assert "a échoué" in result.stderr
    assert not stamp.exists()
    # L'échec du cache de construction n'empêche pas la purge des images.
    assert _calls(tmp_path) == ["builder prune -a -f", "image prune -f"]


def test_prune_invalid_interval_skips_without_failing(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp"
    result = _run(tmp_path, stamp, "0")
    assert result.returncode == 0
    assert _calls(tmp_path) == []
    assert not stamp.exists()


def test_prune_never_touches_volumes_or_system() -> None:
    """Garde anti-régression : ni system prune, ni volume prune."""
    commands = [
        line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")
    ]
    body = "\n".join(commands)
    assert "system prune" not in body
    assert "volume prune" not in body
