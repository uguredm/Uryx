"""SQLAlchemy ORM modelleri (persistence katmanı).

Not: Birincil anahtarlar taşınabilirlik için ``String(36)`` UUID'dir; bu sayede
testler SQLite üzerinde, üretim PostgreSQL üzerinde aynı modelle çalışır.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

def utcnow() -> datetime:
    """Zaman dilimi bilgisi taşıyan UTC zaman damgası."""
    return datetime.now(UTC)

def new_id() -> str:
    """Yeni UUID4 kimliği (string)."""
    return str(uuid.uuid4())

class Base(DeclarativeBase):
    """Tüm ORM modellerinin taban sınıfı."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {dict: JSON, list: JSON}

class MessageRole(str, enum.Enum):
    """Sohbet mesajı rolü."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class ToolCallStatus(str, enum.Enum):
    """Araç çağrısı yaşam döngüsü."""

    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class MemoryCategory(str, enum.Enum):
    """Uzun süreli hafıza kategorileri."""

    PREFERENCE = "preference"
    SYSTEM_INFO = "system_info"
    PROJECT = "project"
    FOLDER = "folder"
    APPLICATION = "application"
    CONTACT = "contact"
    FACT = "fact"
    OTHER = "other"

class DocumentStatus(str, enum.Enum):
    """Belge indeksleme durumu."""

    PENDING = "pending"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"

class Conversation(Base):
    """Bir sohbet oturumu."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), default="Yeni sohbet")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_conversations_updated_at", "updated_at"),)

class Message(Base):
    """Sohbet içindeki tek bir mesaj."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, native_enum=False))
    content: Mapped[str] = mapped_column(Text, default="")
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conv_created", "conversation_id", "created_at"),)

class ToolCall(Base):
    """LLM tarafından tetiklenen bir araç çağrısı kaydı."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(120), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[ToolCallStatus] = mapped_column(
        Enum(ToolCallStatus, native_enum=False), default=ToolCallStatus.PENDING
    )
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    required_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Memory(Base):
    """Uzun süreli hafıza kaydı."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[MemoryCategory] = mapped_column(
        Enum(MemoryCategory, native_enum=False), default=MemoryCategory.OTHER
    )
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(30), default="auto")
    source_conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_memories_active_pinned", "active", "pinned"),
        Index("ix_memories_category", "category"),
    )

class Document(Base):
    """RAG'e eklenmiş bir belge."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(500))
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stored_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream")
    extension: Mapped[str] = mapped_column(String(20), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    collection: Mapped[str] = mapped_column(String(60), default="documents")
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False), default=DocumentStatus.PENDING, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

class DocumentChunk(Base):
    """Belgenin vektörleştirilmiş parçası.

    Chunk metni PostgreSQL'de de tutulur; hybrid retrieval'in sparse (full-text)
    ayağı bu tablo üzerinden çalışır.
    """

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),)

class AppSetting(Base):
    """Sunucu tarafında saklanan kullanıcı ayarı (anahtar/değer)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
