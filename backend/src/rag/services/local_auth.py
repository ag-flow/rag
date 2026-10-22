from __future__ import annotations

import asyncio
import time

import asyncpg
import bcrypt


class LocalAuthService:
    """Auth locale : utilisateurs stockés en base, pas en .env.

    `verify` fait un SELECT + bcrypt.checkpw. `user_count` permet au
    frontend et aux endpoints de savoir si le wizard de premier démarrage
    doit s'afficher.
    """

    def __init__(self, *, pool: asyncpg.Pool, ttl_seconds: int) -> None:
        self._pool = pool
        self._ttl_seconds = ttl_seconds

    async def user_count(self) -> int:
        return await self._pool.fetchval("SELECT COUNT(*) FROM users")  # type: ignore[return-value]

    async def verify(self, *, username: str, password: str) -> str | None:
        """Vérifie les credentials. Retourne l'email si valide, None sinon."""
        row = await self._pool.fetchrow(
            "SELECT email, password_hash FROM users WHERE username = $1",
            username,
        )
        if row is None:
            return None
        try:
            valid = await asyncio.to_thread(
                bcrypt.checkpw,
                password.encode("utf-8"),
                row["password_hash"].encode("utf-8"),
            )
        except ValueError:
            return None
        return row["email"] if valid else None

    async def create_user(
        self, *, username: str, email: str, password_hash: str
    ) -> None:
        # Un compte local est admin (toute session locale valide l'est) : le
        # rôle est écrit en base pour qu'il le RESTE s'il se connecte un jour
        # en OIDC (pont par email vérifié, STANDARD OIDC §4).
        await self._pool.execute(
            "INSERT INTO users (username, email, password_hash, role) "
            "VALUES ($1, $2, $3, 'rag-admin')",
            username,
            email,
            password_hash,
        )

    async def db_owner_id(self, username: str) -> str | None:
        """owner_id figé du compte (migration 099) — mis en session au login."""
        owner: str | None = await self._pool.fetchval(
            "SELECT owner_id FROM users WHERE username = $1", username
        )
        return owner

    def build_session_payload(
        self, username: str, email: str, owner_id: str | None = None
    ) -> dict[str, int | str]:
        payload: dict[str, int | str] = {
            "username": username,
            "email": email,
            "expires_at": int(time.time()) + self._ttl_seconds,
        }
        if owner_id:
            payload["owner_id"] = owner_id
        return payload
