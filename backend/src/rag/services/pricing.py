from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

_cache: dict[str, Any] | None = None
_cache_path: Path | None = None


def load_pricing(pricing_file: Path) -> dict[str, Any]:
    """Charge le YAML de tarifs. Résultat mis en cache (rechargé si le path change)."""
    global _cache, _cache_path
    if _cache is not None and _cache_path == pricing_file:
        return _cache
    if not pricing_file.exists():
        log.warning("pricing.file_not_found", path=str(pricing_file))
        return {}
    try:
        with pricing_file.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _cache = data
        _cache_path = pricing_file
        log.info("pricing.loaded", path=str(pricing_file))
        return data
    except Exception as exc:
        log.warning("pricing.load_error", path=str(pricing_file), error=str(exc))
        return {}


def get_model_pricing(
    pricing_data: dict[str, Any],
    provider: str,
    model: str,
) -> dict[str, Any] | None:
    """Retourne les données de pricing pour un (provider, model) donné."""
    providers = pricing_data.get("providers", {})
    prov = providers.get(provider, {})
    for m in prov.get("models", []):
        if m.get("name") == model:
            return dict(m)
    return None
