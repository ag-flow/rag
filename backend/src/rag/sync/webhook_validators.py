from __future__ import annotations

import base64
import hashlib
import hmac


def validate(
    provider: str,
    secret: str,
    headers: dict[str, str],
    raw_body: bytes,
) -> bool:
    """Valide la signature d'un webhook entrant selon le provider git.

    `headers` doit avoir des cles en minuscules.
    Retourne False pour tout provider inconnu ou header manquant.
    """
    match provider:
        case "github":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-hub-signature-256", ""), prefix="sha256="
            )
        case "gitea":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-gitea-signature", ""), prefix=""
            )
        case "gitlab":
            token = headers.get("x-gitlab-token", "")
            return hmac.compare_digest(token.encode(), secret.encode())
        case "bitbucket":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-hub-signature", ""), prefix="sha256="
            )
        case "azure-devops":
            return _validate_azure_basic(secret, headers.get("authorization", ""))
        case _:
            return False


def _validate_hmac_sha256(secret: str, body: bytes, header_value: str, prefix: str) -> bool:
    if not header_value:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    actual = header_value.removeprefix(prefix)
    return hmac.compare_digest(expected, actual)


def _validate_azure_basic(secret: str, auth_header: str) -> bool:
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode()
    except Exception:
        return False
    password = decoded.split(":", 1)[-1]
    return hmac.compare_digest(password.encode(), secret.encode())
