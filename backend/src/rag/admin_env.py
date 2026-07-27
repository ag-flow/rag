from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Clés gérées via l'IHM et persistées dans le fichier admin.env.
KEY_OIDC_CLIENT_SECRET = "RAG_OIDC_CLIENT_SECRET"  # noqa: S105 — nom de variable, pas un secret
KEY_LOCAL_AUTH_DISABLED = "RAG_LOCAL_AUTH_DISABLED"
KEY_PUBLIC_URL = "RAG_PUBLIC_URL"


class AdminEnvStore:
    """Réglages d'auth pilotés par l'IHM, persistés dans un fichier .env dédié.

    Le fichier est inscriptible et **relu à chaud** à chaque accès : une
    modification (via l'IHM ou éditée à la main sur l'hôte pour le break-glass)
    prend effet sans redémarrage. Il ne contient QUE des réglages gérés par
    l'application ; le `.env` principal (master key, secrets DB, session) n'est
    jamais touché.

    Format : lignes `KEY=value`, `#` en commentaire. Les écritures préservent
    les autres lignes et sont atomiques (fichier temporaire + `os.replace`).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    # --- primitives fichier ---

    def _read_all(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        result: dict[str, str] = {}
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
        return result

    def _write_key(self, key: str, value: str) -> None:
        """Met à jour (ou insère) `key`, en préservant les autres lignes.

        Écriture atomique : on écrit un fichier temporaire dans le même
        répertoire puis `os.replace` (rename atomique sur POSIX).
        """
        existing = (
            self._path.read_text(encoding="utf-8").splitlines()
            if self._path.exists()
            else []
        )
        new_line = f"{key}={value}"
        out: list[str] = []
        replaced = False
        for raw in existing:
            stripped = raw.strip()
            is_key = (
                stripped
                and not stripped.startswith("#")
                and stripped.partition("=")[0].strip() == key
            )
            if is_key:
                if not replaced:
                    out.append(new_line)
                    replaced = True
                continue
            out.append(raw)
        if not replaced:
            out.append(new_line)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), prefix=".admin_env.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(out) + "\n")
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # --- accès typés ---

    def get_oidc_client_secret(self) -> str | None:
        return self._read_all().get(KEY_OIDC_CLIENT_SECRET) or None

    def has_oidc_client_secret(self) -> bool:
        return self.get_oidc_client_secret() is not None

    def set_oidc_client_secret(self, value: str) -> None:
        self._write_key(KEY_OIDC_CLIENT_SECRET, value)

    def get_public_url(self) -> str | None:
        """URL publique de l'app fixée depuis l'IHM (page OIDC).

        Absente ou vide ⇒ None : le caller dérive alors l'URL de l'ADRESSE
        D'APPEL du client (`public_base_from_request`). Prioritaire sur le
        RAG_PUBLIC_URL du `.env` principal (souvent périmé — cf. bug
        redirect_uri=localhost du 2026-07-27)."""
        value = self._read_all().get(KEY_PUBLIC_URL, "").strip()
        return value.rstrip("/") or None

    def set_public_url(self, value: str) -> None:
        """Écrit l'URL publique ; chaîne vide = retour au défaut (dérivée de
        l'adresse d'appel)."""
        self._write_key(KEY_PUBLIC_URL, value.strip())

    def is_local_auth_disabled(self) -> bool:
        # Variable absente ⇒ connexion locale activée (disabled = False).
        return self._read_all().get(KEY_LOCAL_AUTH_DISABLED, "false").lower() == "true"

    def set_local_auth_disabled(self, disabled: bool) -> None:
        self._write_key(KEY_LOCAL_AUTH_DISABLED, "true" if disabled else "false")
