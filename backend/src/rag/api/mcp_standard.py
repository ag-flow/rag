from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

from rag.auth.obo import read_obo_actor
from rag.auth.owner import email_to_owner_id
from rag.db.enrichment_lookup import get_enrichment as get_enrichment_db
from rag.db.workspace_search import vector_search
from rag.indexer.providers.factory import make_provider
from rag.secrets.refs import as_vault_ref, is_vault_ref

log = structlog.get_logger(__name__)

# ── Context workspace propagé par requête ────────────────────────────────────


@dataclass(frozen=True)
class _KeyCtx:
    """Contexte d'AUTHENTIFICATION, posé une fois par le dispatcher.

    Ne dépend plus d'un workspace (l'URL MCP n'en porte plus) : la clé est
    identifiée par son empreinte, avec son propriétaire et son niveau d'accès.
    Le workspace ciblé est un PARAMÈTRE de chaque outil, résolu à l'appel.
    """

    owner_id: str
    scope: str  # read | read_write | admin
    config_pool: asyncpg.Pool
    pool_registry: Any
    resolver: Any
    client_provider: Any
    default_vault_name: str | None = None


@dataclass(frozen=True)
class _WsData:
    """Config d'un workspace résolue à l'appel d'un outil (à partir du slug)."""

    workspace_name: str
    rag_cnx: str
    indexer_service: str
    indexer_provider: str
    indexer_model: str
    indexer_api_key_ref: str | None
    indexer_base_url: str | None
    workspace_id: UUID


_ws_ctx: ContextVar[_KeyCtx] = ContextVar("mcp_key_ctx")


class _WorkspaceUnknownError(Exception):
    """Le slug de workspace demandé n'existe pas."""


async def _resolve_ws(key: _KeyCtx, workspace: str) -> _WsData:
    """Charge la config d'un workspace par son slug (= colonne name).

    Accès global : toute clé valide (scope read+) voit tous les workspaces de
    l'instance (les workspaces n'ont pas de propriétaire). Lève
    `_WorkspaceUnknownError` si le slug est inconnu.
    """
    row = await key.config_pool.fetchrow(
        """
        SELECT w.id, w.name, w.rag_cnx,
               ic.provider, ic.model, ic.api_key_ref, ic.base_url, md.service
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
        WHERE w.name = $1
        """,
        workspace,
    )
    if row is None:
        raise _WorkspaceUnknownError(workspace)
    return _WsData(
        workspace_name=row["name"],
        rag_cnx=row["rag_cnx"],
        indexer_service=row["service"],
        indexer_provider=row["provider"],
        indexer_model=row["model"],
        indexer_api_key_ref=row["api_key_ref"],
        indexer_base_url=row["base_url"],
        workspace_id=row["id"],
    )


_UNKNOWN_WS_MSG = (
    "Workspace '{ws}' introuvable. Appelle d'abord list_workspaces() pour "
    "obtenir les slugs accessibles."
)


async def _resolve_indexer_key(key: _KeyCtx, ws: _WsData) -> str | None:
    """Résout la clé API de l'indexeur du workspace (normalisation legacy, BUG-024)."""
    if not ws.indexer_api_key_ref:
        return None
    ref = ws.indexer_api_key_ref
    if is_vault_ref(ref) or key.default_vault_name is not None:
        return await key.resolver.resolve_with_retry(
            as_vault_ref(ref, key.default_vault_name or "")
        )
    log.warning("mcp_standard.logical_ref_without_default_vault", workspace=ws.workspace_name)
    return None

# ── FastMCP server (singleton, stateless) ────────────────────────────────────

# streamable_http_path="/" : l'app interne répond à la RACINE de son mount →
# l'endpoint public est exactement `/mcp` (sans quoi ce serait `/mcp/mcp`).
# transport_security sans DNS-rebinding protection : ragflow est derrière un
# reverse-proxy de confiance (Caddy + Cloudflare) et le Host public
# (rag.yoops.org) n'est pas dans la liste localhost par défaut — sans ça, tout
# handshake depuis le domaine public serait rejeté.
_mcp = FastMCP(
    "rag",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@_mcp.tool()
async def rag_search(
    workspace: str,
    query: str,
    top_k: int = 5,
    min_score: float = 0.3,
    enrichment_keys: list[str] | None = None,
    scope: str = "both",
) -> str:
    """Recherche par similarité sémantique (embeddings) dans le corpus indexé d'un workspace.

    Trouve les passages dont le SENS est proche de la requête, même si les mots exacts
    n'apparaissent pas. Idéal pour des questions en langue naturelle, des concepts, des
    intentions. Ne fait PAS de correspondance littérale — utiliser search_files pour ça.

    Paramètres :
    - workspace : slug du workspace où chercher (voir list_workspaces pour la liste)
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
    key = _ws_ctx.get()
    try:
        ws = await _resolve_ws(key, workspace)
    except _WorkspaceUnknownError:
        return _UNKNOWN_WS_MSG.format(ws=workspace)

    api_key = await _resolve_indexer_key(key, ws)
    provider = make_provider(
        service=ws.indexer_service,
        provider=ws.indexer_provider,
        model=ws.indexer_model,
        api_key=api_key,
        base_url=ws.indexer_base_url,
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await key.pool_registry.get_workspace_pool(ws.workspace_name, ws.rag_cnx)
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ws.workspace_name,
        indexer_used=f"{ws.indexer_provider}/{ws.indexer_model}",
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

    log.info("mcp_standard.search", workspace=ws.workspace_name, hits=len(hits), scope=scope)
    return "\n\n---\n\n".join(parts)


@_mcp.tool()
async def get_enrichment(workspace: str, path: str, key: str) -> str:
    """Retourne le résultat d'analyse pré-calculée associé à un fichier et à une clé.

    Les enrichissements sont des métadonnées structurées générées sur chaque fichier
    lors de l'indexation : listes de fonctions publiques, résumés, signatures de classes,
    graphes de dépendances, imports, etc. Chaque type d'analyse a une clé distincte.

    Workflow recommandé :
    1. Appeler rag_search avec scope='enriched_only' pour découvrir quels fichiers ont
       des enrichissements et quelles clés existent.
    2. Appeler get_enrichment(workspace, path, key) pour lire un enrichissement précis.

    Paramètres :
    - workspace : slug du workspace (voir list_workspaces)
    - path : chemin exact du fichier tel qu'indexé (ex. "src/auth/middleware.py")
    - key  : clé de l'enrichissement (ex. "public_functions", "summary", "imports")

    Sortie : contenu brut si result_type=text, JSON indenté si result_type=json.
    Retourne un message d'erreur (pas d'exception) si le fichier ou la clé est introuvable.
    Lecture seule. Accède à la base config, pas à la base workspace.
    """
    import json as _json

    key_ctx = _ws_ctx.get()
    try:
        ws = await _resolve_ws(key_ctx, workspace)
    except _WorkspaceUnknownError:
        return _UNKNOWN_WS_MSG.format(ws=workspace)
    data = await get_enrichment_db(
        key_ctx.config_pool,
        workspace_id=ws.workspace_id,
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
async def index_status(workspace: str, path: str | None = None) -> str:
    """Vérifie si l'index d'un workspace est à jour et opérationnel.

    Appeler cet outil avant rag_search ou get_document pour s'assurer que les données
    sont fraîches. Un index en erreur ou vide produira des résultats incomplets ou absents.

    - workspace : slug du workspace (voir list_workspaces)

    Sans path — état global du workspace :
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

    key_ctx = _ws_ctx.get()
    try:
        ws = await _resolve_ws(key_ctx, workspace)
    except _WorkspaceUnknownError:
        return _UNKNOWN_WS_MSG.format(ws=workspace)
    if path:
        data = await get_document_status(
            key_ctx.config_pool, workspace_id=ws.workspace_id, path=path
        )
        if data is None:
            return f"Document '{path}' non trouvé dans l'index."
        return _json.dumps(data, ensure_ascii=False, indent=2)
    data = await get_index_status(key_ctx.config_pool, workspace_id=ws.workspace_id)
    return _json.dumps({"workspace": ws.workspace_name, **data}, ensure_ascii=False, indent=2)


@_mcp.tool()
async def search_files(
    workspace: str,
    pattern: str,
    mode: str = "exact",
    top_k: int = 20,
) -> str:
    """Recherche exhaustive par correspondance littérale dans le corpus indexé.

    - workspace : slug du workspace (voir list_workspaces)

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

    key_ctx = _ws_ctx.get()
    try:
        ws = await _resolve_ws(key_ctx, workspace)
    except _WorkspaceUnknownError:
        return _UNKNOWN_WS_MSG.format(ws=workspace)
    ws_pool = await key_ctx.pool_registry.get_workspace_pool(ws.workspace_name, ws.rag_cnx)
    hits = await search_files_in_workspace(ws_pool, pattern=pattern, mode=mode, top_k=top_k)

    if not hits:
        return f"Aucune occurrence de '{pattern}' trouvée (mode={mode})."

    parts = []
    for h in hits:
        label = h["path"]
        if h.get("enrichment_key"):
            label = f"{h.get('source_path') or h['path']} [{h['enrichment_key']}]"
        parts.append(f"[{label} — chunk {h['chunk_index']}]\n{h['content']}")

    log.info("mcp_standard.search_files", workspace=ws.workspace_name, hits=len(hits), mode=mode)
    return f"**{len(hits)} fichier(s)** contenant '{pattern}' :\n\n" + "\n\n---\n\n".join(parts)


@_mcp.tool()
async def get_document(workspace: str, path: str) -> str:
    """Retourne le contenu complet d'un document depuis l'index (sans accès au disque).

    - workspace : slug du workspace (voir list_workspaces)

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

    key_ctx = _ws_ctx.get()
    try:
        ws = await _resolve_ws(key_ctx, workspace)
    except _WorkspaceUnknownError:
        return _UNKNOWN_WS_MSG.format(ws=workspace)

    # Vérifier le flag allow_full_read
    allow = await key_ctx.config_pool.fetchval(
        "SELECT allow_full_read FROM workspaces WHERE id = $1",
        ws.workspace_id,
    )
    if allow is False:
        return (
            "Lecture complète non autorisée pour ce workspace. "
            "Utilisez rag_search pour des extraits contextuels."
        )

    ws_pool = await key_ctx.pool_registry.get_workspace_pool(ws.workspace_name, ws.rag_cnx)
    result = await reconstruct_document(
        ws_pool, key_ctx.config_pool, workspace_id=ws.workspace_id, path=path
    )

    if result is None:
        return f"Document '{path}' non trouvé dans l'index."

    header = f"**{path}** ({result['sections_count']} section(s))"
    if result["is_code_structured"]:
        header += " — reconstruction par symboles (pas ligne à ligne)"
    if result["is_legacy"]:
        header += " — engine legacy (chunks plats)"

    log.info("mcp_standard.get_document", workspace=ws.workspace_name, path=path)
    return f"{header}\n\n{result['content']}"


@_mcp.tool()
async def list_workspaces() -> str:
    """Liste les workspaces accessibles à la clé — À APPELER EN PREMIER.

    Renvoie l'inventaire des corpus interrogeables : leur slug (identifiant à
    passer en paramètre `workspace` des autres outils), leur nom d'affichage et
    leur description. Aucun paramètre.

    Sortie : JSON {"scope": "read|read_write|admin", "workspaces": [
        {"nom": "...", "slug": "...", "description": "..."}, ...]}.
    Le `scope` est le niveau d'accès de la clé (read = lecture/recherche,
    read_write = + indexation, admin = + gestion de bibliothèque).
    Lecture seule.
    """
    import json as _json

    key_ctx = _ws_ctx.get()
    rows = await key_ctx.config_pool.fetch(
        "SELECT name, label, description FROM workspaces ORDER BY name"
    )
    workspaces = [
        {"nom": r["label"] or r["name"], "slug": r["name"], "description": r["description"] or ""}
        for r in rows
    ]
    return _json.dumps(
        {"scope": key_ctx.scope, "workspaces": workspaces}, ensure_ascii=False, indent=2
    )


# ── Outils de bibliothèque (stratégies de chunking + templates de prompts) ──
# Import en bas de fichier : les outils ont besoin du singleton `_mcp` et du
# ContextVar `_ws_ctx` déjà définis, sans créer d'import circulaire.
from rag.api.mcp_library_tools import register_library_tools  # noqa: E402

register_library_tools(_mcp, _ws_ctx)


def build_mcp_asgi() -> Starlette:
    """Retourne l'app Starlette FastMCP (stateless).

    Réinitialise le session manager avant de (re)construire l'app :
    `StreamableHTTPSessionManager.run()` est à usage unique, or `_mcp` est un
    singleton module. Sans ce reset, reconstruire l'app (tests) relancerait
    `run()` sur le même manager → RuntimeError. En prod build_app n'est appelé
    qu'une fois — le reset est un no-op fonctionnel."""
    _mcp._session_manager = None
    return _mcp.streamable_http_app()


def mcp_session_lifespan() -> Any:
    """Context manager async démarrant le task group du session manager MCP.

    FastAPI n'exécute PAS le lifespan des sous-apps montées : sans entrer ce
    contexte dans le lifespan principal, le serveur streamable répond
    « Task group is not initialized » à chaque handshake. À utiliser autour du
    `yield` du lifespan de main.py. `build_mcp_asgi()` doit avoir été appelé
    avant (il initialise le session_manager)."""
    return _mcp.session_manager.run()


# ── Helpers (exportés pour les tests) ────────────────────────────────────────


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

    Connecteur UNIQUE (plus de workspace_id dans l'URL) :
    - Valide le Bearer token via user_api_keys (empreinte SHA-256, non révoquée).
    - Injecte le contexte d'authentification (owner_id, scope) dans _ws_ctx.
    - Le workspace ciblé est un PARAMÈTRE de chaque outil, résolu à l'appel.
    - Délègue à l'inner FastMCP app sans réécrire le path.
    """

    def __init__(self, inner: ASGIApp) -> None:
        self._inner = inner
        self._config_pool: asyncpg.Pool | None = None
        self._pool_registry: Any = None
        self._resolver: Any = None
        self._client_provider: Any = None

    def set_app_state(self, app_state: Any) -> None:
        """Appelé depuis le lifespan après initialisation des pools."""
        self._config_pool = app_state.pools.config_pool
        self._pool_registry = app_state.pools
        self._resolver = app_state.resolver
        self._client_provider = app_state.client_provider

    async def _resolve_obo_owner(self, actor_login: str) -> str | None:
        """Mappe le login acteur (owner_login portail) → owner_id rag.

        Via le référentiel `users` (username → email → sha256(email)). Introuvable
        (ex. utilisateur OIDC sans ligne locale) → None : on garde l'identité de
        la clé (fail-safe), jamais de refus."""
        assert self._config_pool is not None  # noqa: S101
        email = await self._config_pool.fetchval(
            "SELECT email FROM users WHERE username = $1", actor_login
        )
        if email is None:
            log.warning("mcp.obo.actor_unmapped", actor=actor_login)
            return None
        return email_to_owner_id(email)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._inner(scope, receive, send)
            return

        token = _extract_bearer(list(scope.get("headers", [])))
        if token is None:
            await _json_error(send, 401, "authorization_required")
            return

        if self._config_pool is None:
            await _json_error(send, 503, "service_not_ready")
            return

        try:
            ctx = await self._load_context(token)
        except PermissionError:
            await _json_error(send, 401, "invalid_token")
            return

        # OBO : si le portail a propagé une identité humaine SIGNÉE (secret = le
        # Bearer de cette requête), l'attribution bascule sur cet humain au lieu
        # du propriétaire de la clé. En-tête absent/mal signé → ignoré (jamais
        # 401), on garde l'identité de la clé. Contrat globals d0e2dad3.
        actor = read_obo_actor(list(scope.get("headers", [])), token)
        if actor is not None:
            obo_owner = await self._resolve_obo_owner(actor)
            if obo_owner is not None:
                ctx = replace(ctx, owner_id=obo_owner)

        # Le mount Starlette "/mcp" ampute le préfixe : une requête sur `/mcp`
        # nu arrive ici avec un path vide → normalisé sur "/" pour matcher la
        # route racine de l'app streamable interne.
        if scope.get("path", "") == "":
            scope = {**scope, "path": "/", "raw_path": b"/"}

        token_var = _ws_ctx.set(ctx)
        try:
            await self._inner(scope, receive, send)
        finally:
            _ws_ctx.reset(token_var)

    async def _load_context(self, token: str) -> _KeyCtx:
        assert self._config_pool is not None  # noqa: S101
        fingerprint = sha256(token.encode()).hexdigest()

        # Clés utilisateur : seule l'empreinte SHA-256 est stockée. Toute clé
        # valide (non révoquée, hors grâce) est authentifiée ; l'autorisation
        # fine (scope) est appliquée par chaque outil.
        row = await self._config_pool.fetchrow(
            """
            SELECT owner_id, scope
            FROM user_api_keys
            WHERE fingerprint = $1
              AND revoked_at IS NULL
              AND (rotated_at IS NULL OR rotated_at > now() - interval '72 hours')
            """,
            fingerprint,
        )
        if row is None:
            raise PermissionError("invalid token")

        default_vault_name: str | None = None
        if self._client_provider is not None:
            default_vault_name = await self._client_provider.get_default_vault_name()

        return _KeyCtx(
            owner_id=str(row["owner_id"]),
            scope=str(row["scope"]),
            config_pool=self._config_pool,
            pool_registry=self._pool_registry,
            resolver=self._resolver,
            client_provider=self._client_provider,
            default_vault_name=default_vault_name,
        )


async def _json_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"error": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"application/json"]],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})
