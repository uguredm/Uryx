"""Sohbet ve WebSocket protokolü şemaları.

Sunucu→istemci olayları ``type`` alanıyla ayrışan bir union oluşturur;
TypeScript karşılığı ``packages/shared-types/src/ws.ts`` içindedir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

class ConversationSummary(ORMModel):
    """Sohbet listesi öğesi."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    archived: bool

class MessageOut(ORMModel):
    """Tek mesaj."""

    id: str
    conversation_id: str
    role: str
    content: str
    thinking: str | None = None
    created_at: datetime
    token_count: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)

class ConversationDetail(ConversationSummary):
    """Mesajlarıyla birlikte sohbet."""

    summary: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)

class CreateConversationRequest(BaseModel):
    """Yeni sohbet isteği."""

    title: str = Field(default="Yeni sohbet", max_length=300)

class RenameConversationRequest(BaseModel):
    """Sohbet yeniden adlandırma."""

    title: str = Field(min_length=1, max_length=300)

class ChatOptions(BaseModel):
    """Tek bir sohbet isteğine özel seçenekler."""

    use_rag: bool = True
    use_memory: bool = True
    use_tools: bool = True
    thinking: bool = False
    concise: bool = False
    tts: bool = False
    tts_voice: str | None = Field(default=None, max_length=100)
    tts_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=16, le=32768)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    require_confirmation: bool = True
    language: Literal["tr", "en"] | None = None

class ChatRequest(BaseModel):
    """REST (non-streaming) sohbet isteği."""

    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=32000)
    options: ChatOptions = Field(default_factory=ChatOptions)

class SourceRef(BaseModel):
    """Cevapta kullanılan RAG kaynağı."""

    chunk_id: str
    document_id: str
    filename: str
    score: float
    snippet: str
    page: int | None = None

class MemoryRef(BaseModel):
    """Cevapta kullanılan hafıza kaydı."""

    id: str
    content: str
    category: str
    score: float

class ChatResponse(BaseModel):
    """REST sohbet cevabı."""

    conversation_id: str
    message_id: str
    content: str
    thinking: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    memories: list[MemoryRef] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str = "stop"

class WSUserMessage(BaseModel):
    """Kullanıcının gönderdiği mesaj."""

    type: Literal["user_message"] = "user_message"
    conversation_id: str | None = None
    content: str = Field(min_length=1, max_length=32000)
    options: ChatOptions = Field(default_factory=ChatOptions)

class WSToolConfirmResponse(BaseModel):
    """Kullanıcının araç onayı cevabı."""

    type: Literal["tool_confirm_response"] = "tool_confirm_response"
    request_id: str
    approved: bool

    remember: bool = False

    fingerprint: str | None = None

class WSCancel(BaseModel):
    """Aktif üretimi iptal et."""

    type: Literal["cancel"] = "cancel"

class WSPing(BaseModel):
    """Bağlantı canlılık kontrolü."""

    type: Literal["ping"] = "ping"

WSClientEvent = WSUserMessage | WSToolConfirmResponse | WSCancel | WSPing

class WSStart(BaseModel):
    """Üretim başladı."""

    type: Literal["start"] = "start"
    conversation_id: str
    message_id: str

class WSToken(BaseModel):
    """Cevap parçası."""

    type: Literal["token"] = "token"
    content: str

class WSThinking(BaseModel):
    """Düşünme (reasoning) parçası."""

    type: Literal["thinking"] = "thinking"
    content: str

class WSToolCall(BaseModel):
    """Araç çağrısı başlatıldı."""

    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool_name: str
    display_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

class WSToolResult(BaseModel):
    """Araç sonucu."""

    type: Literal["tool_result"] = "tool_result"
    call_id: str
    tool_name: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

class WSToolConfirmRequest(BaseModel):
    """Riskli araç için kullanıcı onayı isteği."""

    type: Literal["tool_confirm_request"] = "tool_confirm_request"
    request_id: str
    tool_name: str
    display_name: str
    description: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "medium"
    impact: str = ""
    fingerprint: str = ""
    remember_allowed: bool = False
    irreversible: bool = False

    confirmation_ticket: str = ""

class WSSources(BaseModel):
    """Kullanılan RAG kaynakları."""

    type: Literal["sources"] = "sources"
    sources: list[SourceRef] = Field(default_factory=list)

class WSMemoryUsed(BaseModel):
    """Prompt'a eklenen hafıza kayıtları."""

    type: Literal["memory_used"] = "memory_used"
    memories: list[MemoryRef] = Field(default_factory=list)

class WSMemoryCreated(BaseModel):
    """Konuşmadan çıkarılan yeni hafıza kaydı."""

    type: Literal["memory_created"] = "memory_created"
    id: str
    content: str
    category: str
    importance: float

class WSTTSChunk(BaseModel):
    """Base64 kodlanmış ses parçası."""

    type: Literal["tts_chunk"] = "tts_chunk"
    index: int
    audio_base64: str
    mime_type: str = "audio/wav"
    text: str = ""
    voice: str | None = None
    speed: float | None = None

class WSTTSStatus(BaseModel):
    """Seslendirme durumu."""

    type: Literal["tts_status"] = "tts_status"
    state: Literal["started", "finished", "error", "disabled"]
    detail: str | None = None

class WSDone(BaseModel):
    """Üretim tamamlandı."""

    type: Literal["done"] = "done"
    conversation_id: str
    message_id: str
    content: str
    finish_reason: str = "stop"
    elapsed_ms: int = 0

class WSError(BaseModel):
    """Hata olayı."""

    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

class WSPong(BaseModel):
    """Ping cevabı."""

    type: Literal["pong"] = "pong"

WSServerEvent = (
    WSStart
    | WSToken
    | WSThinking
    | WSToolCall
    | WSToolResult
    | WSToolConfirmRequest
    | WSSources
    | WSMemoryUsed
    | WSMemoryCreated
    | WSTTSChunk
    | WSTTSStatus
    | WSDone
    | WSError
    | WSPong
)
