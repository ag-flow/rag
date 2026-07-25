from __future__ import annotations

from fastapi import Request


def public_base_from_request(request: Request) -> str:
    """URL publique de base résolue depuis l'ADRESSE D'APPEL.

    Host réellement utilisé par le client (`X-Forwarded-Host` derrière proxy,
    sinon `Host`). Schéma : derrière un proxy public (`X-Forwarded-Host`
    présent), le TLS est terminé en amont (Cloudflare/Caddy) et le hop interne
    est en HTTP — `X-Forwarded-Proto` reflète ce hop, pas l'entrée publique :
    on force `https`. Sans proxy, on honore `X-Forwarded-Proto` (premier
    maillon si liste) puis l'URL de la requête.

    Plus fiable que `RAG_PUBLIC_URL` pour les URLs renvoyées au CLIENT
    (contrats, redirections logout) : reflète le domaine exact de l'appel même
    quand la config est erronée."""
    fwd_host = request.headers.get("x-forwarded-host")
    host = fwd_host or request.headers.get("host")
    if not host:
        return str(request.base_url).rstrip("/")
    if fwd_host:
        scheme = "https"
    else:
        proto = request.headers.get("x-forwarded-proto")
        scheme = proto.split(",")[0].strip() if proto else request.url.scheme
    return f"{scheme}://{host}"
