from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/jobs/{job_id}/logs")
async def ws_job_logs(job_id: str, websocket: WebSocket) -> None:
    """Stream des logs d'un job de synchro en temps réel.

    Pas d'auth — le job_id UUID est difficile à deviner.
    Envoie d'abord le replay_buffer, puis les nouveaux événements.
    Ferme proprement quand l'event 'done' arrive ou que le client déconnecte.
    """
    await websocket.accept()
    bus = websocket.app.state.job_log_bus
    replay, q = bus.subscribe(job_id)
    try:
        for event in replay:
            await websocket.send_text(json.dumps(event))

        if replay and replay[-1].get("type") == "done":
            return

        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            await websocket.send_text(json.dumps(event))
            if event.get("type") == "done":
                break
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(job_id, q)
