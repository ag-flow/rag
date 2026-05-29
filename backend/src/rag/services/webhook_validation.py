from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

# Plages d'adresses interdites (loopback, privées, link-local, CGNAT…)
_PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),   # RFC 6598 — CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),   # RFC 2544 — benchmark
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # ULA
    ipaddress.ip_network("fe80::/10"),       # link-local IPv6
]

# RFC 7230 — token : tout sauf séparateurs
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_FORBIDDEN_VALUE_CHARS = frozenset({"\r", "\n", "\x00"})


def validate_webhook_url(url: str) -> None:
    """Lève ValueError si l'URL présente un risque SSRF.

    Vérifie : schéma http/https, absence de credentials, résolution DNS
    vers une adresse publique uniquement.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"URL non parseable : {exc}") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Schéma interdit {parsed.scheme!r} — seuls http et https sont acceptés"
        )

    if parsed.username or parsed.password:
        raise ValueError("L'URL ne doit pas contenir de credentials (user:pass@host)")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("L'URL n'a pas de hostname")

    # IP littérale dans l'URL — vérification directe sans DNS
    try:
        ip = ipaddress.ip_address(hostname)
        _assert_public(ip, hostname)
        return
    except ValueError:
        pass  # Pas une IP littérale, on fait la résolution DNS

    # Résolution DNS synchrone (acceptable pour les opérations admin)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError as exc:
        raise ValueError(f"Impossible de résoudre {hostname!r} : {exc}") from exc

    for info in infos:
        raw = str(info[4][0])
        try:
            _assert_public(ipaddress.ip_address(raw), raw)
        except ValueError:
            raise  # re-raise SSRF error


def _assert_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, label: str) -> None:
    if any(ip in net for net in _PRIVATE_NETWORKS):
        raise ValueError(
            f"L'URL pointe vers une adresse privée/réservée : {label}"
        )


def validate_header_name(name: str) -> None:
    """Lève ValueError si le nom de header ne respecte pas RFC 7230 §3.2.6."""
    if not _HEADER_NAME_RE.match(name):
        raise ValueError(
            f"Nom de header invalide {name!r} — doit respecter la syntaxe token RFC 7230"
        )


def validate_header_value(value: str) -> None:
    """Lève ValueError si la valeur contient des caractères d'injection HTTP."""
    if any(c in value for c in _FORBIDDEN_VALUE_CHARS):
        raise ValueError(
            "La valeur du header contient des caractères interdits (CR, LF ou NUL)"
        )
