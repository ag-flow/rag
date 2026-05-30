from __future__ import annotations

import asyncio
from hashlib import sha256
from typing import Any

import asyncpg
import structlog

from rag.services.llm_clients import call_llm

log = structlog.get_logger(__name__)


async def _resolve_harpo(
    harpo_path: str, vault_svc: Any, client_provider: Any, config_pool: Any
) -> str | None:
    from rag.secrets.refs import is_vault_ref, parse_ref
    if not is_vault_ref(harpo_path):
        return None
    vault_name, secret_path = parse_ref(harpo_path)
    async with config_pool.acquire() as conn:
        vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        return None
    client = await client_provider.get_client(vault.api_key_id)
    return await asyncio.to_thread(client.get_secret, secret_path)


async def run_enrichments(
    *,
    conn: asyncpg.Connection,
    indexer: Any,
    workspace_id: str,
    workspace_name: str,
    path: str,
    content: str,
    content_hash: str,
    vault_svc: Any,
    client_provider: Any,
    config_pool: Any | None = None,
) -> list[dict[str, Any]]:
    """Exécute les trigger prompts actifs pour l'extension de `path`."""
    import pathlib
    extension = pathlib.Path(path).suffix.lower()
    if not extension:
        return []

    trigger_prompts = await conn.fetch(
        """
        SELECT
            tp.id AS tp_id,
            tp.template_id,
            pt.name AS template_name,
            pt.metadata_key,
            pt.result_type,
            pt.prompt,
            tp.llm_id,
            lc.provider AS llm_provider,
            lc.model AS llm_model,
            lc.api_key_ref,
            lc.base_url AS llm_base_url
        FROM workspace_extension_trigger_prompts tp
        JOIN workspace_extension_triggers t ON t.id = tp.trigger_id
        JOIN workspaces w ON w.id = t.workspace_id
        JOIN prompt_templates pt ON pt.id = tp.template_id
        JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
        WHERE w.id = $1::uuid
          AND t.extension = $2
          AND t.enabled = true
          AND tp.enabled = true
          AND lc.enabled = true
        ORDER BY tp.order_index
        """,
        workspace_id,
        extension,
    )

    if not trigger_prompts:
        return []

    results: list[dict[str, Any]] = []
    src_hash = content_hash.removeprefix("sha256:")

    for row in trigger_prompts:
        template_id = str(row["template_id"])
        metadata_key = row["metadata_key"]
        enriched_path = f"{path}::{metadata_key}"

        existing = await conn.fetchrow(
            "SELECT id, result_hash FROM document_enrichments "
            "WHERE workspace_id = $1::uuid AND path = $2 AND template_id = $3::uuid",
            workspace_id, path, template_id,
        )

        if existing and existing["result_hash"] == src_hash:
            results.append({
                "path": path,
                "metadata_key": metadata_key,
                "template": row["template_name"],
                "result_type": row["result_type"],
                "status": "skipped",
            })
            continue

        llm_api_key: str | None = None
        if row["api_key_ref"] and config_pool:
            llm_api_key = await _resolve_harpo(
                row["api_key_ref"], vault_svc, client_provider, config_pool
            )

        prompt_text = row["prompt"].replace("{content}", content)

        llm_result = await call_llm(
            provider=row["llm_provider"],
            model=row["llm_model"],
            api_key=llm_api_key,
            base_url=row["llm_base_url"],
            system_prompt="",
            messages=[{"role": "user", "content": prompt_text}],
        )
        answer = (llm_result["answer"] or "").strip()

        if not answer:
            await indexer.delete_file(workspace_id=workspace_id, path=enriched_path)
            if existing:
                await conn.execute(
                    "DELETE FROM document_enrichments WHERE id = $1::uuid", existing["id"]
                )
            results.append({
                "path": path,
                "metadata_key": metadata_key,
                "template": row["template_name"],
                "result_type": row["result_type"],
                "status": "empty",
                "previous_enrichment_deleted": existing is not None,
            })
            continue

        await indexer.index_file(
            workspace_id=workspace_id,
            path=enriched_path,
            content=answer,
            content_hash=f"sha256:{sha256(answer.encode()).hexdigest()}",
            indexer_used=f"{row['llm_provider']}/{row['llm_model']}",
        )

        await conn.execute(
            """
            INSERT INTO document_enrichments
                (workspace_id, path, template_id, metadata_key, result_type,
                 result, result_hash, llm_provider, llm_model, indexed_at)
            VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6, $7, $8, $9, now())
            ON CONFLICT (workspace_id, path, template_id)
            DO UPDATE SET
                result = EXCLUDED.result,
                result_hash = EXCLUDED.result_hash,
                llm_provider = EXCLUDED.llm_provider,
                llm_model = EXCLUDED.llm_model,
                indexed_at = now()
            """,
            workspace_id, path, template_id, metadata_key,
            row["result_type"], answer, src_hash,
            row["llm_provider"], row["llm_model"],
        )

        log.info("enrichment.done", workspace=workspace_name, path=path, metadata_key=metadata_key)
        results.append({
            "path": path,
            "metadata_key": metadata_key,
            "template": row["template_name"],
            "result_type": row["result_type"],
            "status": "done",
        })

    return results
