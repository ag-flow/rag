from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID


class IndexerProtocol(Protocol):
    """Frontière entre le sync worker (M3) et le moteur d'indexation (M4).

    M3 utilise `NoOpIndexer` qui maintient seulement `indexed_documents`.
    M4 remplacera par `RealIndexer` qui ajoute chunking + embeddings +
    upsert pgvector dans la base `rag_<workspace_name>`.
    """

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
        title: str | None = None,
        strategy_id: UUID | None = None,
        extra_metadata: Mapping[str, Any] | None = None,
        source_url: str | None = None,
    ) -> int:
        """Index un fichier. Retourne le nombre de chunks créés.

        - `workspace_id` : workspace cible (sert au routing du pool pgvector).
        - `path` : chemin relatif au worktree (clé d'upsert).
        - `content` : contenu UTF-8 du fichier.
        - `content_hash` : `sha256:<hex>` du contenu.
        - `indexer_used` : `<provider>/<model>` au moment de l'indexation
          (sert à invalider les hashes si l'indexeur change).
        - `strategy_id` : stratégie LIÉE par id (spec chunking §5 — résolue
          en amont, à l'acceptation du push) ; prime sur le routage par
          extension. Ignoré en moteur `legacy`. Le mode job n'a jamais de
          contexte utilisateur : seul un id déjà lié circule jusqu'ici.
        """
        ...

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        """Supprime tous les chunks pgvector d'un fichier + DELETE
        `indexed_documents`. Idempotent.
        """
        ...
