from __future__ import annotations

from typing import Any

from rag.schemas.vault_endpoints import (
    EndpointIndexerSpec,
    EndpointLlmSpec,
    EndpointOut,
    EndpointRerankSpec,
    EndpointUpdate,
)
from rag.services.endpoint_sharing import UsableEndpoint

SERVICES = ("vectorization", "rerank", "llm")


def service_summary(ep: EndpointOut) -> dict[str, Any]:
    """Résumé {service: {provider, model} | None} pour le listing."""

    def _spec(spec: Any) -> dict[str, Any] | None:
        if spec is None:
            return None
        return {"provider": spec.provider, "model": spec.model}

    return {
        "vectorization": _spec(ep.indexer),
        "rerank": _spec(ep.rerank),
        "llm": _spec(ep.llm),
    }


def shared_endpoint_groups(usable: list[UsableEndpoint]) -> list[dict[str, Any]]:
    """Groupes du listing pour les endpoints PARTAGÉS avec l'appelant (095).

    Leurs coffres ne sont pas visibles de lui : on n'expose que le nom et le
    label du coffre (pour désigner l'endpoint) et le résumé des services — ni
    refs de secrets ni configuration, et jamais `writable`.
    """
    groups: dict[str, dict[str, Any]] = {}
    for ep in usable:
        if ep.access != "shared":
            continue
        group = groups.setdefault(
            ep.vault_name,
            {
                "vault": ep.vault_name,
                "vault_label": ep.vault_label,
                "writable": False,
                "shared": True,
                "endpoints": [],
            },
        )
        group["endpoints"].append(
            {
                "slug": ep.slug,
                "label": ep.label,
                "services": {
                    "vectorization": _pair(ep.indexer),
                    "rerank": _pair(ep.rerank),
                    "llm": _pair(ep.llm),
                },
            }
        )
    return list(groups.values())


def _pair(spec: tuple[str, str] | None) -> dict[str, str] | None:
    return None if spec is None else {"provider": spec[0], "model": spec[1]}


def _merge_spec(
    spec_cls: type,
    current: Any,
    *,
    provider: str | None,
    model: str | None,
    api_key_ref: str | None,
    base_url: str | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    max_concurrency: int | None,
    extra: dict[str, Any],
) -> Any:
    """Fusionne les champs fournis avec la section courante (None = conservé).

    Sentinelles d'effacement explicites : `api_key_ref=""` / `base_url=""`
    retirent la valeur ; `rpm_limit=0` / `tpm_limit=0` / `max_concurrency=0`
    désactivent la règle.
    """

    def _text(new: str | None, old: str | None) -> str | None:
        if new is None:
            return old
        return None if new == "" else new

    def _limit(new: int | None, old: int | None) -> int | None:
        if new is None:
            return old
        return None if new == 0 else new

    values: dict[str, Any] = {
        "provider": provider if provider is not None else getattr(current, "provider", None),
        "model": model if model is not None else getattr(current, "model", None),
        "api_key_ref": _text(api_key_ref, getattr(current, "api_key_ref", None)),
        "base_url": _text(base_url, getattr(current, "base_url", None)),
        "rpm_limit": _limit(rpm_limit, getattr(current, "rpm_limit", None)),
        "tpm_limit": _limit(tpm_limit, getattr(current, "tpm_limit", None)),
        "max_concurrency": _limit(max_concurrency, getattr(current, "max_concurrency", None)),
    }
    values.update(extra)
    if values["provider"] is None or values["model"] is None:
        raise ValueError(
            "cette section n'existe pas encore sur l'endpoint : fournis au "
            "minimum `provider` et `model` pour la créer"
        )
    return spec_cls(**values)


def build_service_update(
    ep: EndpointOut,
    *,
    service: str,
    clear: bool,
    provider: str | None,
    model: str | None,
    api_key_ref: str | None,
    base_url: str | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    max_concurrency: int | None,
    top_k_pre_rerank: int | None,
) -> EndpointUpdate:
    """Traduit la mise à jour partielle d'UN service en EndpointUpdate complet."""
    if clear:
        if service == "vectorization":
            raise ValueError("la vectorisation est obligatoire : clear impossible")
        return EndpointUpdate(clear_rerank=service == "rerank", clear_llm=service == "llm")

    common = {
        "provider": provider,
        "model": model,
        "api_key_ref": api_key_ref,
        "base_url": base_url,
        "rpm_limit": rpm_limit,
        "tpm_limit": tpm_limit,
        "max_concurrency": max_concurrency,
    }
    if service == "vectorization":
        spec = _merge_spec(EndpointIndexerSpec, ep.indexer, **common, extra={})
        return EndpointUpdate(indexer=spec)
    if service == "rerank":
        extra = {
            "top_k_pre_rerank": (
                top_k_pre_rerank
                if top_k_pre_rerank is not None
                else (ep.rerank.top_k_pre_rerank if ep.rerank else 20)
            )
        }
        spec = _merge_spec(EndpointRerankSpec, ep.rerank, **common, extra=extra)
        return EndpointUpdate(rerank=spec)
    return EndpointUpdate(llm=_merge_spec(EndpointLlmSpec, ep.llm, **common, extra={}))
