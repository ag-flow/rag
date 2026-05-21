from __future__ import annotations

import time

import bcrypt


class LocalAuthService:
    """Auth locale bootstrap : un seul user `admin`, hash bcrypt en .env.

    Le service est `enabled` si et seulement si `password_hash` est non vide.
    `verify` est constant-time grace a `bcrypt.checkpw`. Aucune validation
    au boot du format du hash : un hash invalide fait simplement echouer le
    login (False), pas de fail-fast.
    """

    def __init__(
        self,
        *,
        username: str,
        password_hash: str,
        ttl_seconds: int,
    ) -> None:
        self._username = username
        self._password_hash = password_hash
        self._ttl_seconds = ttl_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._password_hash.strip())

    @property
    def username(self) -> str:
        return self._username

    def verify(self, *, username: str, password: str) -> bool:
        if not self.enabled:
            return False
        if username != self._username:
            return False
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                self._password_hash.encode("utf-8"),
            )
        except ValueError:
            # Hash malforme — ne crashe pas, simplement login refuse.
            return False

    def build_session_payload(self) -> dict[str, int | str]:
        return {
            "username": self._username,
            "expires_at": int(time.time()) + self._ttl_seconds,
        }
