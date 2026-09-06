"""Sohbet WebSocket endpoint'i (``/ws/chat``).

Protokol için bkz. ``app/schemas/chat.py`` ve ``packages/shared-types/src/ws.ts``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.api.deps import get_ws_container
from app.core.errors import UryxError, UnauthorizedError
from app.core.locale import loc, set_ui_language
from app.core.logging import get_logger
from app.core.security import require_ws_token
from app.schemas.chat import (
    ChatOptions,
    WSError,
    WSPong,
    WSToolConfirmRequest,
)
from app.services.tools.policy import ConfirmDecision

logger = get_logger(__name__)
router = APIRouter()

CONFIRMATION_TIMEOUT = 120.0

class ChatSession:
    """Tek bir WebSocket bağlantısının durumu."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.send_lock = asyncio.Lock()
        self.pending_confirmations: dict[str, asyncio.Future[ConfirmDecision]] = {}
        self.pending_tickets: dict[str, str] = {}
        self.active_turn: asyncio.Task[Any] | None = None

    async def emit(self, event: BaseModel) -> None:
        """Sunucu olayını istemciye gönderir."""
        async with self.send_lock:
            await self.websocket.send_json(event.model_dump(mode="json"))

    async def confirm(self, request: WSToolConfirmRequest) -> ConfirmDecision:
        """Kullanıcıdan araç onayı ister ve cevabı bekler.

        Zaman aşımında veya bağlantı koptuğunda güvenli varsayılan reddir.
        """
        future: asyncio.Future[ConfirmDecision] = asyncio.get_running_loop().create_future()
        self.pending_confirmations[request.request_id] = future
        if request.confirmation_ticket:
            self.pending_tickets[request.request_id] = request.confirmation_ticket
        try:
            await self.emit(request)
            return await asyncio.wait_for(future, timeout=CONFIRMATION_TIMEOUT)
        except TimeoutError:
            logger.info("tool_confirmation_timeout", tool=request.tool_name)
            return ConfirmDecision(approved=False, reason="timeout")
        except (WebSocketDisconnect, RuntimeError):
            logger.info("tool_confirmation_timeout", tool=request.tool_name)
            return ConfirmDecision(approved=False, reason="cancelled")
        finally:
            self.pending_confirmations.pop(request.request_id, None)
            self.pending_tickets.pop(request.request_id, None)

    def resolve_confirmation(
        self,
        request_id: str,
        approved: bool,
        *,
        remember: bool = False,
        fingerprint: str | None = None,
    ) -> None:
        """Kullanıcının onay cevabını bekleyen çağrıya iletir."""
        future = self.pending_confirmations.get(request_id)
        if future is not None and not future.done():
            future.set_result(
                ConfirmDecision(
                    approved=approved,
                    remember=remember and approved,
                    reason="approved" if approved else "rejected",
                    fingerprint=fingerprint,
                    ticket=self.pending_tickets.get(request_id),
                )
            )

    def cancel_turn(self, *, revoke_ticket: Callable[[str | None], None] | None = None) -> None:
        """Aktif üretimi iptal eder; onay biletini yakar (mcp_call TOCTOU)."""
        if self.active_turn is not None and not self.active_turn.done():
            self.active_turn.cancel()
        for request_id, future in list(self.pending_confirmations.items()):
            if not future.done():
                future.set_result(ConfirmDecision(approved=False, reason="cancelled"))
            ticket = self.pending_tickets.get(request_id)
            if ticket and callable(revoke_ticket):
                revoke_ticket(ticket)

@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """Streaming sohbet bağlantısı."""
    try:
        await require_ws_token(websocket, websocket.query_params.get("token"))
    except UnauthorizedError:
        await websocket.close(code=4401, reason=loc("Geçersiz token", "Invalid token"))
        return

    await websocket.accept()
    set_ui_language(websocket.query_params.get("lang"))
    container = get_ws_container(websocket)
    session = ChatSession(websocket)
    logger.info("chat_ws_connected")

    try:
        while True:
            raw = await websocket.receive_json()
            await _dispatch(raw, session, container)
    except WebSocketDisconnect:
        logger.info("chat_ws_disconnected")
    except (ValueError, TypeError) as exc:
        logger.warning("chat_ws_bad_payload", error=str(exc))
        await _safe_close(websocket, 1003, loc("Geçersiz mesaj biçimi", "Invalid message format"))
    except Exception as exc:
        logger.exception("chat_ws_error", error=str(exc))
        await _safe_close(websocket, 1011, loc("Sunucu hatası", "Server error"))
    finally:
        session.cancel_turn(revoke_ticket=container.executor.tickets.revoke)

async def _dispatch(raw: Any, session: ChatSession, container: Any) -> None:
    """Gelen istemci olayını işler."""
    if not isinstance(raw, dict):
        await session.emit(
            WSError(code="bad_request", message=loc("Mesaj bir nesne olmalı.", "Message must be an object."))
        )
        return

    event_type = str(raw.get("type", ""))

    if event_type == "ping":
        await session.emit(WSPong())
        return

    if event_type == "cancel":
        session.cancel_turn(revoke_ticket=container.executor.tickets.revoke)
        return

    if event_type == "tool_confirm_response":
        session.resolve_confirmation(
            str(raw.get("request_id", "")),
            bool(raw.get("approved", False)),
            remember=bool(raw.get("remember", False)),
            fingerprint=str(raw["fingerprint"]) if raw.get("fingerprint") else None,
        )
        return

    if event_type != "user_message":
        await session.emit(
            WSError(
                code="unknown_event",
                message=loc(
                    f"Bilinmeyen olay türü: {event_type}",
                    f"Unknown event type: {event_type}",
                ),
            )
        )
        return

    content = str(raw.get("content", "")).strip()
    if not content:
        await session.emit(WSError(code="validation_error", message=loc("Mesaj boş olamaz.", "Message cannot be empty.")))
        return
    if len(content) > 32000:
        await session.emit(
            WSError(
                code="validation_error",
                message=loc(
                    "Mesaj çok uzun (en fazla 32000 karakter).",
                    "Message is too long (32000 characters max).",
                ),
            )
        )
        return

    try:
        options = ChatOptions.model_validate(raw.get("options") or {})
    except PydanticValidationError as exc:
        await session.emit(
            WSError(
                code="validation_error",
                message=loc("Seçenekler doğrulanamadı.", "Options could not be validated."),
                details={"errors": exc.error_count()},
            )
        )
        return

    if session.active_turn is not None and not session.active_turn.done():
        await session.emit(
            WSError(
                code="busy",
                message=loc(
                    "Önceki cevap hâlâ üretiliyor. Lütfen bekleyin.",
                    "The previous reply is still generating. Please wait.",
                ),
            )
        )
        return

    session.active_turn = asyncio.create_task(
        _run_turn(session, container, raw.get("conversation_id"), content, options)
    )

async def _run_turn(
    session: ChatSession,
    container: Any,
    conversation_id: str | None,
    content: str,
    options: ChatOptions,
) -> None:
    """Bir sohbet turunu çalıştırır ve hataları istemciye bildirir."""
    try:
        await container.orchestrator.run_turn(
            conversation_id=conversation_id,
            user_message=content,
            options=options,
            emit=session.emit,
            confirm=session.confirm,
        )
    except asyncio.CancelledError:
        with suppress(RuntimeError, WebSocketDisconnect):
            await session.emit(
                WSError(
                    code="cancelled",
                    message=loc(
                        "Cevap üretimi kullanıcı tarafından durduruldu.",
                        "Reply generation was stopped by the user.",
                    ),
                )
            )
        raise
    except UryxError as exc:
        container.system.set_last_error(exc.user_message)
        await _emit_safe(
            session, WSError(code=exc.code, message=exc.user_message, details=exc.details)
        )
    except Exception as exc:
        logger.exception("chat_turn_failed")
        container.system.set_last_error(str(exc))
        await _emit_safe(
            session,
            WSError(
                code="internal_error",
                message=loc(
                    f"Beklenmeyen bir hata oluştu: {exc}",
                    f"An unexpected error occurred: {exc}",
                ),
            ),
        )

async def _emit_safe(session: ChatSession, event: BaseModel) -> None:
    """Bağlantı kapanmışsa sessizce geçer."""
    with suppress(RuntimeError, WebSocketDisconnect):
        await session.emit(event)

async def _safe_close(websocket: WebSocket, code: int, reason: str) -> None:
    """Bağlantıyı güvenli biçimde kapatır."""
    with suppress(RuntimeError):
        await websocket.close(code=code, reason=reason)
