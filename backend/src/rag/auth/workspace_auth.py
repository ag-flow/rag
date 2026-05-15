from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID


@dataclass
class _CacheEntry:
    workspace_id: UUID
    indexer_used: str
    inserted_at: float


class ApiKeyCache:
    """Cache LRU+TTL des api_keys workspace validées par bcrypt.

    Clé : (workspace_name, api_key_clair). Valeur : _CacheEntry.

    Le cache ne contient que des entrées dont la vérification bcrypt a réussi.
    Un attaquant qui présente une clé invalide paie bcrypt à chaque tentative,
    sans pollution du cache (LRU évincte tout de toute façon).
    """

    def __init__(self, *, max_size: int = 256, ttl_seconds: int = 300) -> None:
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()

    def get(self, workspace_name: str, api_key: str) -> _CacheEntry | None:
        key = (workspace_name, api_key)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.inserted_at > self._ttl_seconds:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry

    def put(self, workspace_name: str, api_key: str, entry: _CacheEntry) -> None:
        key = (workspace_name, api_key)
        self._store[key] = entry
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, workspace_name: str) -> None:
        to_delete = [k for k in self._store if k[0] == workspace_name]
        for k in to_delete:
            del self._store[k]
