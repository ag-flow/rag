from __future__ import annotations

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
            valid = bcrypt.checkpw(
                password.encode("utf-8"),
                row["password_hash"].encode("utf-8"),
            )
        except ValueError:
            return None
        return row["email"] if valid else None

    async def create_user(
        self, *, username: str, email: str, password_hash: str
    ) -> None:
        await self._pool.execute(
            "INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3)",
            username,
            email,
            password_hash,
        )

    def build_session_payload(self, username: str, email: str) -> dict[str, int | str]:
        return {
            "username": username,
            "email": email,
            "expires_at": int(time.time()) + self._ttl_seconds,
        }
