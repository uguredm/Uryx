"""Sohbet REST endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DatabaseDep, OrchestratorDep
from app.core.errors import LLMUnavailableError, NotFoundError
from app.core.security import require_token
from app.db.repositories.conversation import (
    ConversationRepository,
    MessageRepository,
    ToolCallRepository,
)
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
    MessageOut,
    RenameConversationRequest,
)
from app.schemas.common import OkResponse

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_token)])

@router.post("", response_model=ChatResponse, summary="Akışsız sohbet")
async def chat(request: ChatRequest, orchestrator: OrchestratorDep) -> ChatResponse:
    """Tek seferlik (streaming olmayan) sohbet cevabı üretir.

    Gerçek zamanlı deneyim için ``/ws/chat`` WebSocket'i tercih edilmelidir;
    bu endpoint script ve test amaçlıdır. Onay gerektiren araçlar burada
    otomatik olarak reddedilir.
    """

    async def _noop_emit(_event: object) -> None:
        return None

    result = await orchestrator.run_turn(
        conversation_id=request.conversation_id,
        user_message=request.message,
        options=request.options,
        emit=_noop_emit,
        confirm=None,
    )

    if result.get("error"):
        raise LLMUnavailableError(str(result["error"]))

    return ChatResponse(
        conversation_id=result["conversation_id"],
        message_id=result["message_id"],
        content=result["content"],
        thinking=result.get("thinking") or None,
        sources=result["sources"],
        memories=result["memories"],
        tool_calls=result["tool_calls"],
        finish_reason=result.get("finish_reason", "stop"),
    )

conversations = APIRouter(
    prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_token)]
)

@conversations.get("", response_model=list[ConversationSummary], summary="Sohbetleri listele")
async def list_conversations(
    database: DatabaseDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
) -> list[ConversationSummary]:
    """Sohbet geçmişini en son güncellenenden başlayarak listeler."""
    async with database.session() as session:
        repo = ConversationRepository(session)
        records = (
            await repo.search(search, limit=limit)
            if search
            else await repo.list_recent(limit=limit, offset=offset)
        )
        return [ConversationSummary.model_validate(r) for r in records]

@conversations.post(
    "",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni sohbet",
)
async def create_conversation(
    payload: CreateConversationRequest, database: DatabaseDep
) -> ConversationSummary:
    """Yeni bir sohbet oturumu açar."""
    async with database.session() as session:
        conversation = await ConversationRepository(session).create(payload.title)
        await session.flush()
        return ConversationSummary.model_validate(conversation)

@conversations.get("/{conversation_id}", response_model=ConversationDetail, summary="Sohbet detayı")
async def get_conversation(conversation_id: str, database: DatabaseDep) -> ConversationDetail:
    """Sohbeti mesajlarıyla birlikte döndürür."""
    async with database.session() as session:
        conversation = await ConversationRepository(session).get_with_messages(conversation_id)
        if conversation is None:
            raise NotFoundError("Sohbet bulunamadı.")
        return ConversationDetail.model_validate(conversation)

@conversations.get(
    "/{conversation_id}/messages", response_model=list[MessageOut], summary="Sohbet mesajları"
)
async def list_messages(
    conversation_id: str,
    database: DatabaseDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[MessageOut]:
    """Sohbetin mesajlarını kronolojik sırayla döndürür."""
    async with database.session() as session:
        records = await MessageRepository(session).list_for_conversation(
            conversation_id, limit=limit
        )
        return [MessageOut.model_validate(r) for r in records]

@conversations.patch("/{conversation_id}", response_model=OkResponse, summary="Sohbeti adlandır")
async def rename_conversation(
    conversation_id: str, payload: RenameConversationRequest, database: DatabaseDep
) -> OkResponse:
    """Sohbet başlığını değiştirir."""
    async with database.session() as session:
        repo = ConversationRepository(session)
        if await repo.get(conversation_id) is None:
            raise NotFoundError("Sohbet bulunamadı.")
        await repo.rename(conversation_id, payload.title)
    return OkResponse(message="Sohbet yeniden adlandırıldı.")

@conversations.delete("/{conversation_id}", response_model=OkResponse, summary="Sohbeti sil")
async def delete_conversation(conversation_id: str, database: DatabaseDep) -> OkResponse:
    """Sohbeti ve mesajlarını siler."""
    async with database.session() as session:
        deleted = await ConversationRepository(session).delete(conversation_id)
    if not deleted:
        raise NotFoundError("Sohbet bulunamadı.")
    return OkResponse(message="Sohbet silindi.")

@conversations.get("/{conversation_id}/tool-calls", summary="Sohbetteki araç çağrıları")
async def list_conversation_tool_calls(
    conversation_id: str, database: DatabaseDep
) -> list[dict[str, object]]:
    """Sohbette çalıştırılmış araçları döndürür."""
    async with database.session() as session:
        calls = await ToolCallRepository(session).list_for_conversation(conversation_id)
    return [
        {
            "id": c.id,
            "tool_name": c.tool_name,
            "arguments": c.arguments,
            "status": c.status.value if hasattr(c.status, "value") else c.status,
            "risk_level": c.risk_level,
            "approved": c.approved,
            "duration_ms": c.duration_ms,
            "error": c.error,
            "created_at": c.created_at.isoformat(),
        }
        for c in calls
    ]
