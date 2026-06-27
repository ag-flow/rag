from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog
import yaml

log = structlog.get_logger(__name__)

_VALID_STRATEGIES = frozenset({"replace", "append"})
_STRATEGY_FILE = Path(".rag") / "strategy.yml"


def parse_strategy_file(
    repo_path: Path,
) -> dict[str, Literal["replace", "append"]]:
    """Lit `.rag/strategy.yml` dans `repo_path` et retourne un dict path → strategy.

    Retourne un dict vide si le fichier est absent, malformé ou sans clé `strategies`.
    Les valeurs inconnues sont silencieusement ignorées.
    """
    yml_path = repo_path / _STRATEGY_FILE
    if not yml_path.exists():
        return {}

    try:
        raw = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("strategy_config.parse_error", path=str(yml_path), error=str(exc))
        return {}

    if not isinstance(raw, dict):
        return {}

    strategies_raw = raw.get("strategies")
    if not isinstance(strategies_raw, dict):
        return {}

    result: dict[str, Literal["replace", "append"]] = {}
    for path, value in strategies_raw.items():
        if value in _VALID_STRATEGIES:
            result[str(path)] = value  # type: ignore[assignment]
        else:
            log.warning(
                "strategy_config.unknown_strategy",
                path=str(path),
                value=value,
            )
    return result
