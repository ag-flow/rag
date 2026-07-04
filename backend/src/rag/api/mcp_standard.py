from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

from rag.db.enrichment_lookup import get_enrichment as get_enrichment_db
from rag.db.workspace_search import vector_search
from rag.indexer.providers.factory import make_provider
from rag.secrets.refs import is_vault_ref

log = structlog.get_logger(__name__)

# ── Context workspace propagé par requête ────────────────────────────────────


@dataclass(frozen=True)
class _WsCtx:
    workspace_name: str
    rag_cnx: str
    indexer_service: str
    indexer_provider: str
    indexer_model: str
    indexer_api_key_ref: str | None
    indexer_base_url: str | None
    pool_registry: Any
    resolver: Any
    workspace_id: UUID
    config_pool: asyncpg.Pool


_ws_ctx: ContextVar[_WsCtx] = ContextVar("mcp_ws_ctx")

# ── FastMCP server (singleton, stateless) ────────────────────────────────────

_mcp = FastMCP("rag", stateless_http=True)


@_mcp.tool()
async def rag_search(
    query: str,
    top_k: int = 5,
    min_score: float = 0.3,
    enrichment_keys: list[str] | None = None,
    scope: str = "both",
) -> str:
    """Recherche par similarité sémantique (embeddings) dans le corpus indexé du workspace.

    Trouve les passages dont le SENS est proche de la requête, même si les mots exacts
    n'apparaissent pas. Idéal pour des questions en langue naturelle, des concepts, des
    intentions. Ne fait PAS de correspondance littérale — utiliser search_files pour ça.

    Paramètres :
    - query     : la question ou le concept (texte libre, n'importe quelle langue)
    - top_k     : nombre de passages à retourner (défaut 5 ; au-delà de 20 le ratio
                  signal/bruit baisse)
    - min_score : seuil de similarité cosinus [0-1] ; en dessous, le résultat est écarté.
                  0.3 (défaut) = seuil permissif. Monter à 0.5-0.7 pour les questions
                  précises où seuls les passages très proches ont de la valeur.
    - scope     : 'both' (défaut) — code source + enrichissements ;
                  'raw_only'      — code source uniquement (ignore les métadonnées) ;
                  'enriched_only' — enrichissements uniquement (résumés, listes de
                                   fonctions, graphes de dépendances…)
    - enrichment_keys : restreint aux enrichissements de ces types précis
                        (ex. ['public_functions', 'summary']). Ignoré si scope='raw_only'.

    Sortie : passages triés par score décroissant, format [path — chunk N — score 0.XXX]
    suivi du texte. Lecture seule, n'accède qu'au contenu indexé (pas aux fichiers live).
    """
    ctx = _ws_ctx.get()

    api_key: str | None = None
    if ctx.indexer_api_key_ref and is_vault_ref(ctx.indexer_api_key_ref):
        api_key = await ctx.resolver.resolve_with_retry(ctx.indexer_api_key_ref)

    provider = make_provider(
        service=ctx.indexer_service,
        provider=ctx.indexer_provider,
        model=ctx.indexer_model,
        api_key=api_key,
        base_url=ctx.indexer_base_url,
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ctx.workspace_name,
        indexer_used=f"{ctx.indexer_provider}/{ctx.indexer_model}",
        scope=scope,
        enrichment_keys=enrichment_keys,
    )

    if not hits:
        return "Aucun résultat pertinent trouvé dans le corpus."

    parts = []
    for h in hits:
        label = h.path
        if h.enrichment_key:
            label = f"{h.source_path or h.path} [{h.enrichment_key}]"
        parts.append(f"[{label} — chunk {h.chunk_index} — score {h.score:.3f}]\n{h.content}")

    log.info("mcp_standard.search", workspace=ctx.workspace_name, hits=len(hits), scope=scope)
    return "\n\n---\n\n".join(parts)


@_mcp.tool()
async def get_enrichment(path: str, key: str) -> str:
    """Retourne le résultat d'analyse pré-calculée associé à un fichier et à une clé.

    Les enrichissements sont des métadonnées structurées générées sur chaque fichier
    lors de l'indexation : listes de fonctions publiques, résumés, signatures de classes,
    graphes de dépendances, imports, etc. Chaque type d'analyse a une clé distincte.

    Workflow recommandé :
    1. Appeler rag_search avec scope='enriched_only' pour découvrir quels fichiers ont
       des enrichissements et quelles clés existent.
    2. Appeler get_enrichment(path, key) pour lire le détail d'un enrichissement précis.

    Paramètres :
    - path : chemin exact du fichier tel qu'indexé (ex. "src/auth/middleware.py")
    - key  : clé de l'enrichissement (ex. "public_functions", "summary", "imports")

    Sortie : contenu brut si result_type=text, JSON indenté si result_type=json.
    Retourne un message d'erreur (pas d'exception) si le fichier ou la clé est introuvable.
    Lecture seule. Accède à la base config, pas à la base workspace.
    """
    import json as _json

    ctx = _ws_ctx.get()
    data = await get_enrichment_db(
        ctx.config_pool,
        workspace_id=ctx.workspace_id,
        path=path,
        key=key,
    )
    if data is None:
        return f"Aucun enrichissement '{key}' trouvé pour '{path}'."
    result = data["result"]
    if data["result_type"] == "json":
        try:
            return _json.dumps(_json.loads(result), ensure_ascii=False, indent=2)
        except _json.JSONDecodeError:
            return result
    return result


@_mcp.tool()
async def index_status(path: str | None = None) -> str:
    """Vérifie si l'index du workspace est à jour et opérationnel.

    Appeler cet outil avant rag_search ou get_document pour s'assurer que les données
    sont fraîches. Un index en erreur ou vide produira des résultats incomplets ou absents.

    Sans argument — état global du workspace :
    - documents_count   : nombre de fichiers actuellement indexés
    - last_indexed_at   : horodatage de la dernière indexation (null = index vide)
    - sync.healthy      : false si le dernier job s'est terminé en erreur ; true sinon
                          (y compris si aucun job n'a encore tourné)
    - sync.last_job_status : 'done' | 'error' | 'skipped' | null
    - sync.next_sync_at : prochaine indexation planifiée (null si sync manuel)

    Avec path (ex. index_status("src/auth.py")) — état d'un fichier précis :
    - indexed_at   : quand ce fichier a été indexé pour la dernière fois
    - content_hash : SHA256 du contenu indexé (comparer avec le fichier source pour
                     détecter une dérive entre l'index et la réalité)
    - indexer_used : modèle d'embedding utilisé pour ce fichier

    Retourne un message d'erreur si le fichier n'est pas dans l'index.
    Lecture seule. Requête sur la base config, pas la base workspace.
    """
    import json as _json

    from rag.db.mcp_tools import get_document_status, get_index_status

    ctx = _ws_ctx.get()
    if path:
        data = await get_document_status(ctx.config_pool, workspace_id=ctx.workspace_id, path=path)
        if data is None:
            return f"Document '{path}' non trouvé dans l'index."
        return _json.dumps(data, ensure_ascii=False, indent=2)
    data = await get_index_status(ctx.config_pool, workspace_id=ctx.workspace_id)
    return _json.dumps({"workspace": ctx.workspace_name, **data}, ensure_ascii=False, indent=2)


@_mcp.tool()
async def search_files(
    pattern: str,
    mode: str = "exact",
    top_k: int = 20,
) -> str:
    """Recherche exhaustive par correspondance littérale dans le corpus indexé.

    Contrairement à rag_search (sémantique), cette recherche est déterministe :
    elle trouve TOUTES les occurrences d'un motif exact. Utiliser pour retrouver
    un identifiant précis, un nom de variable, une constante, une chaîne littérale.

    Modes :
    - 'exact'     (défaut) : tokenisation FTS — trouve le token exact, sans stemming ni
                  troncature. Rapide (index GIN). Recommandé pour les identifiants comme
                  RAG_MASTER_KEY ou nom_de_fonction. ATTENTION : ne trouve pas les
                  sous-chaînes partielles ("MASTER" ne retrouve pas "RAG_MASTER_KEY").
    - 'substring' : ILIKE '%motif%' — trouve toute sous-chaîne, insensible à la casse.
                  Utile quand le motif est un fragment de token. Plus lent que 'exact'.
    - 'regex'     : opérateur Postgres ~ — expressions régulières complètes.
                  Très lent sur grand corpus (scan séquentiel, pas d'index).
                  Réserver aux cas où exact et substring ne suffisent pas.

    top_k : nombre maximum de FICHIERS DISTINCTS retournés. Un seul extrait de chunk
    est retourné par fichier, même si plusieurs chunks contiennent le motif.

    Sortie : [path — chunk N] + extrait du chunk correspondant, séparés par ---.
    Recherche dans le contenu INDEXÉ uniquement, pas sur le disque. Lecture seule.
    """
    from rag.db.mcp_tools import search_files_in_workspace

    ctx = _ws_ctx.get()
    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    hits = await search_files_in_workspace(ws_pool, pattern=pattern, mode=mode, top_k=top_k)

    if not hits:
        return f"Aucune occurrence de '{pattern}' trouvée (mode={mode})."

    parts = []
    for h in hits:
        label = h["path"]
        if h.get("enrichment_key"):
            label = f"{h.get('source_path') or h['path']} [{h['enrichment_key']}]"
        parts.append(f"[{label} — chunk {h['chunk_index']}]\n{h['content']}")

    log.info("mcp_standard.search_files", workspace=ctx.workspace_name, hits=len(hits), mode=mode)
    return f"**{len(hits)} fichier(s)** contenant '{pattern}' :\n\n" + "\n\n---\n\n".join(parts)


@_mcp.tool()
async def get_document(path: str) -> str:
    """Retourne le contenu complet d'un document depuis l'index (sans accès au disque).

    Utile pour lire un fichier entier quand le filesystem n'est pas disponible (agent cloud,
    conteneur sans montage). Le document est RECONSTRUIT depuis les sections stockées en base —
    ce n'est pas le fichier source original, mais sa représentation indexée.

    Comportement selon le type de fichier :
    - Prose / Markdown / Data : reconstruction fidèle dans l'ordre des sections déclarées.
    - Code (analysé par tree-sitter) : reconstruction par symboles (fonctions, classes, blocs).
      L'ordre est correct mais le contenu entre symboles (imports isolés, commentaires flottants)
      peut être incomplet. NE PAS utiliser pour obtenir des numéros de ligne exacts.

    Cas particuliers :
    - Workspace en mode restreint (allow_full_read=False) : appel refusé avec un message
      explicite — utiliser rag_search pour des extraits contextuels à la place.
    - Fichier indexé avec l'ancien engine (legacy, sans sections) : reconstruction depuis
      les chunks plats dans leur ordre d'indexation. Mentionné dans la sortie.
    - Fichier absent de l'index : message d'erreur, pas d'exception.

    Pour vérifier qu'un fichier est indexé avant d'appeler : index_status(path).
    Lecture seule. Ne modifie pas l'index.
    """
    from rag.db.mcp_tools import reconstruct_document

    ctx = _ws_ctx.get()

    # Vérifier le flag allow_full_read
    allow = await ctx.config_pool.fetchval(
        "SELECT allow_full_read FROM workspaces WHERE id = $1",
        ctx.workspace_id,
    )
    if allow is False:
        return (
            "Lecture complète non autorisée pour ce workspace. "
            "Utilisez rag_search pour des extraits contextuels."
        )

    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    result = await reconstruct_document(
        ws_pool, ctx.config_pool, workspace_id=ctx.workspace_id, path=path
    )

    if result is None:
        return f"Document '{path}' non trouvé dans l'index."

    header = f"**{path}** ({result['sections_count']} section(s))"
    if result["is_code_structured"]:
        header += " — reconstruction par symboles (pas ligne à ligne)"
    if result["is_legacy"]:
        header += " — engine legacy (chunks plats)"

    log.info("mcp_standard.get_document", workspace=ctx.workspace_name, path=path)
    return f"{header}\n\n{result['content']}"


def build_mcp_asgi() -> Starlette:
    """Retourne l'app Starlette FastMCP (stateless). Appelé une seule fois."""
    return _mcp.streamable_http_app()


# ── Helpers (exportés pour les tests) ────────────────────────────────────────


def _extract_workspace_id(path: str) -> str | None:
    """Extrait et valide le premier segment du path comme UUID workspace."""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    candidate = segments[0]
    try:
        UUID(candidate)
    except ValueError:
        return None
    return candidate


def _extract_bearer(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Extrait le token Bearer du header Authorization."""
    for name, value in headers:
        if name.lower() == b"authorization":
            decoded = value.decode()
            if decoded.startswith("Bearer "):
                return decoded[7:]
    return None


# ── ASGI Dispatcher ──────────────────────────────────────────────────────────


class RagMcpDispatcher:
    """Dispatcher ASGI monté sur /mcp dans FastAPI.

    - Extrait workspace_id du path (/{workspace_id}/...)
    - Valide le Bearer token via workspace_api_keys
    - Injecte le contexte workspace dans _ws_ctx
    - Réécrit le path (supprime le segment workspace_id)
    - Délègue à l'inner FastMCP app
    """

    def __init__(self, inner: ASGIApp) -> None:
        self._inner = inner
        self._config_pool: asyncpg.Pool | None = None
        self._pool_registry: Any = None
        self._resolver: Any = None
        self._apikey_cache: Any = None

    def set_app_state(self, app_state: Any) -> None:
        """Appelé depuis le lifespan après initialisation des pools."""
        self._config_pool = app_state.pools.config_pool
        self._pool_registry = app_state.pools
        self._resolver = app_state.resolver
        self._apikey_cache = app_state.apikey_cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._inner(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        workspace_id = _extract_workspace_id(path)
        if workspace_id is None:
            await _json_error(send, 404, "workspace_id_required")
            return

        token = _extract_bearer(list(scope.get("headers", [])))
        if token is None:
            await _json_error(send, 401, "authorization_required")
            return

        if self._config_pool is None:
            await _json_error(send, 503, "service_not_ready")
            return

        try:
            ctx = await self._load_context(workspace_id, token)
        except PermissionError:
            await _json_error(send, 401, "invalid_token")
            return
        except LookupError:
            await _json_error(send, 404, "workspace_not_found")
            return

        segments = [s for s in path.split("/") if s]
        remaining = "/" + "/".join(segments[1:]) if len(segments) > 1 else "/"
        new_scope = {**scope, "path": remaining, "raw_path": remaining.encode()}

        token_var = _ws_ctx.set(ctx)
        try:
            await self._inner(new_scope, receive, send)
        finally:
            _ws_ctx.reset(token_var)

    async def _load_context(self, workspace_id: str, token: str) -> _WsCtx:
        assert self._config_pool is not None  # noqa: S101
        fingerprint = sha256(token.encode()).hexdigest()

        row = await self._config_pool.fetchrow(
            """
            SELECT w.name, w.rag_cnx,
                   k.api_key_ref,
                   ic.provider, ic.model,
                   ic.api_key_ref AS indexer_api_key_ref,
                   ic.base_url,
                   md.service
            FROM workspaces w
            JOIN workspace_api_keys k ON k.workspace_id = w.id
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
            WHERE w.id = $1::uuid
              AND k.fingerprint = $2
              AND k.revoked_at IS NULL
              AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
            """,
            workspace_id,
            fingerprint,
        )

        if row is None:
            exists = await self._config_pool.fetchval(
                "SELECT 1 FROM workspaces WHERE id = $1::uuid", workspace_id
            )
            if not exists:
                raise LookupError(workspace_id)
            raise PermissionError("invalid token")

        api_key_ref: str = row["api_key_ref"]
        cached = self._apikey_cache.get(api_key_ref)
        if cached is None:
            cached = await self._resolver.resolve_with_retry(api_key_ref)
            self._apikey_cache.put(api_key_ref, cached)

        if not compare_digest(cached, token):
            raise PermissionError("token mismatch")

        return _WsCtx(
            workspace_name=str(row["name"]),
            rag_cnx=str(row["rag_cnx"]),
            indexer_service=str(row["service"]),
            indexer_provider=str(row["provider"]),
            indexer_model=str(row["model"]),
            indexer_api_key_ref=row["indexer_api_key_ref"],
            indexer_base_url=row["base_url"],
            pool_registry=self._pool_registry,
            resolver=self._resolver,
            workspace_id=UUID(workspace_id),
            config_pool=self._config_pool,
        )


async def _json_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"error": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"application/json"]],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})
