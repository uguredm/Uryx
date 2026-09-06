"""Sistem metriklerini yayınlayan WebSocket (``/ws/system``)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.deps import get_ws_container
from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger
from app.core.security import require_ws_token
from app.schemas.system import WSSystemUpdate

logger = get_logger(__name__)
router = APIRouter()

@router.websocket("/ws/system")
async def system_websocket(websocket: WebSocket) -> None:
    """Belirli aralıklarla sistem durumunu yayınlar."""
    try:
        await require_ws_token(websocket, websocket.query_params.get("token"))
    except UnauthorizedError:
        await websocket.close(code=4401, reason="Geçersiz token")
        return

    await websocket.accept()
    container = get_ws_container(websocket)
    settings = get_settings()
    interval = settings.system_metrics_interval
    logger.info("system_ws_connected", interval=interval)

    reader = asyncio.create_task(_drain(websocket))
    try:
        while True:

            if reader.done() or websocket.client_state is not WebSocketState.CONNECTED:
                break

            status = await container.system.status(use_cache=True)
            await websocket.send_json(WSSystemUpdate(payload=status).model_dump(mode="json"))

            done, _ = await asyncio.wait({reader}, timeout=interval)
            if done:
                break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.warning("system_ws_error", error=str(exc))
    finally:
        reader.cancel()
        logger.info("system_ws_disconnected")

async def _drain(websocket: WebSocket) -> None:
    """İstemciden gelen mesajları tüketir.

    Yayın döngüsü bu görevin bitmesini bağlantı kopuşu sinyali olarak kullanır.
    """
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        return
