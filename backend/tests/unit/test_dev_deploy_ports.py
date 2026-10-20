"""scripts/ports.sh : choix du premier port hôte libre (dev-deploy.sh).

`ss` et `docker` sont remplacés par des doublures en tête du PATH : BUSY_SS
liste les ports « en écoute », BUSY_DOCKER ceux « publiés par un conteneur ».
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[3] / "scripts" / "ports.sh"

# ss reçoit le filtre « ( sport = :N ) » : on en extrait N.
_FAKE_SS = """#!/usr/bin/env bash
port="$(echo "$*" | sed -E 's/.*sport = :([0-9]+).*/\\1/')"
for p in $BUSY_SS; do [ "$p" = "$port" ] && echo "LISTEN 0 4096 0.0.0.0:$p 0.0.0.0:*"; done
exit 0
"""

_FAKE_DOCKER = """#!/usr/bin/env bash
for p in $BUSY_DOCKER; do echo "0.0.0.0:$p->80/tcp, [::]:$p->80/tcp"; done
"""


def _first_free(
    tmp_path: Path, start: int, span: int, *, ss: str = "", docker: str = ""
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("ss", _FAKE_SS), ("docker", _FAKE_DOCKER)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BUSY_SS": ss,
        "BUSY_DOCKER": docker,
    }
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}" && first_free_port {start} {span}'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_first_free_port_keeps_wanted_port_when_free(tmp_path: Path) -> None:
    result = _first_free(tmp_path, 80, 100, ss="8080 180")
    assert (result.returncode, result.stdout.strip()) == (0, "80")


def test_first_free_port_skips_port_held_by_listening_process(tmp_path: Path) -> None:
    result = _first_free(tmp_path, 80, 100, ss="80 81")
    assert result.stdout.strip() == "82"


def test_first_free_port_skips_port_published_by_container_without_socket(
    tmp_path: Path,
) -> None:
    """userland-proxy désactivé : le port n'est visible que via docker ps."""
    result = _first_free(tmp_path, 80, 100, docker="80")
    assert result.stdout.strip() == "81"


def test_first_free_port_does_not_confuse_80_with_8080_or_180(tmp_path: Path) -> None:
    result = _first_free(tmp_path, 80, 100, docker="8080 180")
    assert result.stdout.strip() == "80"


def test_first_free_port_all_taken_fails_without_output(tmp_path: Path) -> None:
    result = _first_free(tmp_path, 80, 2, ss="80 81 82")
    assert result.returncode == 1
    assert result.stdout == ""
