"""İlk şema: sohbetler, mesajlar, araç çağrıları, hafıza, belgeler, ayarlar.

Revision ID: 0001
Revises:
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MESSAGE_ROLES = ("system", "user", "assistant", "tool")
TOOL_STATUSES = (
    "pending",
    "awaiting_confirmation",
    "rejected",
    "running",
    "success",
    "failed",
)
MEMORY_CATEGORIES = (
    "preference",
    "system_info",
    "project",
    "folder",
    "application",
    "contact",
    "fact",
    "other",
)
DOCUMENT_STATUSES = ("pending", "parsing", "embedding", "indexed", "failed")

def upgrade() -> None:
    """Şemayı oluşturur."""

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False, server_default="Yeni sohbet"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum(*MESSAGE_ROLES, name="messagerole", native_enum=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conv_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum(*TOOL_STATUSES, name="toolcallstatus", native_enum=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column(
            "required_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_calls_conversation_id", "tool_calls", ["conversation_id"])
    op.create_index("ix_tool_calls_tool_name", "tool_calls", ["tool_name"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(*MEMORY_CATEGORIES, name="memorycategory", native_enum=False),
            nullable=False,
            server_default="other",
        ),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(30), nullable=False, server_default="auto"),
        sa.Column("source_conversation_id", sa.String(36), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_memories_active_pinned", "memories", ["active", "pinned"])
    op.create_index("ix_memories_category", "memories", ["category"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column(
            "mime_type",
            sa.String(150),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("extension", sa.String(20), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("collection", sa.String(60), nullable=False, server_default="documents"),
        sa.Column(
            "status",
            sa.Enum(*DOCUMENT_STATUSES, name="documentstatus", native_enum=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_document_chunks_fts ON document_chunks "
            "USING GIN (to_tsvector('simple', content))"
        )
        op.execute(
            "CREATE INDEX ix_memories_content_trgm ON memories "
            "USING GIN (content gin_trgm_ops)"
        )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    """Şemayı geri alır."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_memories_content_trgm")
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts")
    op.drop_table("app_settings")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("memories")
    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("conversations")
