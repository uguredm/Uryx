"""Host köprüsü WebSocket'i (``/ws/host``).

Electron main process bu bağlantıyı kurar. Backend, Windows tarafında
çalışması gereken araçları buradan çağırır; Electron da sistem metriklerini
buradan push eder.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_ws_container
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger
from app.core.security import require_ws_token

logger = get_logger(__name__)
router = APIRouter()

@router.websocket("/ws/host")
async def host_websocket(websocket: WebSocket) -> None:
    """Electron ↔ backend RPC köprüsü."""
    try:
        await require_ws_token(websocket, websocket.query_params.get("token"))
    except UnauthorizedError:
        await websocket.close(code=4401, reason="Geçersiz token")
        return

    await websocket.accept()
    container = get_ws_container(websocket)
    bridge = container.host_bridge

    await bridge.attach(
        websocket,
        info={
            "platform": websocket.query_params.get("platform", "unknown"),
            "version": websocket.query_params.get("version", "unknown"),
        },
    )
    await websocket.send_json({"type": "host_bridge_ready"})

    try:
        while True:
            message: Any = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            await _handle(message, container)
    except WebSocketDisconnect:
        pass
    except (ValueError, TypeError) as exc:
        logger.warning("host_ws_bad_payload", error=str(exc))
    except Exception as exc:
        logger.warning("host_ws_error", error=str(exc))
    finally:
        await bridge.detach(websocket)

async def _handle(message: dict[str, Any], container: Any) -> None:
    """Electron'dan gelen mesajı yönlendirir."""
    message_type = str(message.get("type", ""))

    if message_type == "host_tool_response":
        container.host_bridge.resolve(message)
    elif message_type == "host_metrics":
        payload = message.get("payload")
        if isinstance(payload, dict):
            container.host_bridge.update_metrics(payload)
    elif message_type == "host_capabilities":
        container.host_bridge.set_capabilities(message)
    elif message_type == "host_error":
        container.system.set_last_error(str(message.get("message", ""))[:500])
    elif message_type == "ping":
        await container.host_bridge.notify({"type": "pong"})
