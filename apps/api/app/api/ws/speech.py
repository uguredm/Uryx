"""Masaüstü STT akışı — Whisper ``/ws/transcribe`` vekili."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger
from app.core.security import require_ws_token

logger = get_logger(__name__)
router = APIRouter()

@router.websocket("/ws/speech/transcribe")
async def speech_transcribe(websocket: WebSocket) -> None:
    """Electron'dan gelen ses parçalarını Whisper akışına iletir."""
    try:
        await require_ws_token(websocket, websocket.query_params.get("token"))
    except UnauthorizedError:
        await websocket.close(code=4401, reason="Geçersiz token")
        return

    await websocket.accept()
    settings = get_settings()
    base = settings.whisper_url.rstrip("/")
    uri = base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    uri = f"{uri}/ws/transcribe"

    try:
        import websockets

        async with websockets.connect(uri, open_timeout=5, close_timeout=2) as upstream:
            async def down() -> None:
                try:
                    while True:
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            break
                        raw_bytes = message.get("bytes")
                        if raw_bytes:
                            await upstream.send(raw_bytes)
                            continue
                        text = message.get("text")
                        if text:
                            await upstream.send(str(text))
                except WebSocketDisconnect:
                    return

            async def up() -> None:
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        continue
                    await websocket.send_text(raw if isinstance(raw, str) else str(raw))

            await asyncio.gather(down(), up())
    except Exception as exc:
        logger.warning("speech_ws_proxy_failed", error=str(exc))
        try:
            await websocket.send_json({"type": "error", "text": "Whisper akışı yok"})
        except Exception:
            return
