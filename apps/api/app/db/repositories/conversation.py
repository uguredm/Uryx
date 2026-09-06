"""Sohbet, mesaj ve araç çağrısı repository'leri."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import selectinload

from app.db.models import (
    Conversation,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
    utcnow,
)
from app.db.repositories.base import BaseRepository

class ConversationRepository(BaseRepository[Conversation]):
    """Sohbet oturumları."""

    model = Conversation

    async def create(self, title: str = "Yeni sohbet") -> Conversation:
        """Yeni sohbet oluşturur."""
        return await self.add(Conversation(title=title))

    async def get_with_messages(self, conversation_id: str) -> Conversation | None:
        """Mesajlarıyla birlikte sohbeti döndürür."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().one_or_none()

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        """En son güncellenen sohbetleri döndürür."""
        stmt = (
            select(Conversation)
            .where(Conversation.archived.is_(False))
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def touch(self, conversation_id: str) -> None:
        """``updated_at`` ve ``message_count`` alanlarını tazeler."""
        count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        count = int((await self.session.execute(count_stmt)).scalar_one())
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=utcnow(), message_count=count)
        )

    async def rename(self, conversation_id: str, title: str) -> None:
        """Sohbet başlığını değiştirir."""
        await self.session.execute(
            update(Conversation).where(Conversation.id == conversation_id).values(title=title[:300])
        )

    async def set_summary(self, conversation_id: str, summary: str) -> None:
        """Letta tarzı bölüm özetini kalıcılaştırır."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(summary=summary[:4000], updated_at=utcnow())
        )

    async def list_with_summaries(self, limit: int = 40) -> list[Conversation]:
        """Özeti dolu sohbetleri (bölüm geri getirme yedeği) döndürür."""
        stmt = (
            select(Conversation)
            .where(Conversation.archived.is_(False), Conversation.summary.is_not(None))
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def search(self, query: str, limit: int = 20) -> list[Conversation]:
        """Başlık veya mesaj içeriğinde arama yapar."""
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Conversation)
            .join(Message, Message.conversation_id == Conversation.id, isouter=True)
            .where(
                func.lower(Conversation.title).like(pattern)
                | func.lower(func.coalesce(Conversation.summary, "")).like(pattern)
                | func.lower(Message.content).like(pattern)
            )
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

class MessageRepository(BaseRepository[Message]):
    """Sohbet mesajları."""

    model = Message

    async def create(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        *,
        thinking: str | None = None,
        meta: dict[str, Any] | None = None,
        token_count: int = 0,
    ) -> Message:
        """Yeni mesaj kaydeder."""
        return await self.add(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                thinking=thinking,
                meta=meta or {},
                token_count=token_count,
            )
        )

    async def list_for_conversation(
        self, conversation_id: str, *, limit: int = 200
    ) -> list[Message]:
        """Sohbetin mesajlarını kronolojik sırayla döndürür."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def last_n(self, conversation_id: str, n: int) -> list[Message]:
        """Son ``n`` mesajı kronolojik sırayla döndürür (kısa süreli hafıza)."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at), desc(Message.id))
            .limit(n)
        )
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

class ToolCallRepository(BaseRepository[ToolCall]):
    """Araç çağrısı kayıtları."""

    model = ToolCall

    async def create(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        conversation_id: str | None = None,
        risk_level: str = "low",
        required_confirmation: bool = False,
    ) -> ToolCall:
        """Yeni araç çağrısı kaydı açar."""
        return await self.add(
            ToolCall(
                tool_name=tool_name,
                arguments=arguments,
                conversation_id=conversation_id,
                risk_level=risk_level,
                required_confirmation=required_confirmation,
                status=ToolCallStatus.PENDING,
            )
        )

    async def finish(
        self,
        call_id: str,
        *,
        status: ToolCallStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int = 0,
        approved: bool | None = None,
    ) -> None:
        """Araç çağrısını sonlandırır."""
        values: dict[str, Any] = {
            "status": status,
            "result": result or {},
            "error": error,
            "duration_ms": duration_ms,
        }
        if approved is not None:
            values["approved"] = approved
        await self.session.execute(update(ToolCall).where(ToolCall.id == call_id).values(**values))

    async def list_recent(self, limit: int = 50) -> list[ToolCall]:
        """Son araç çağrılarını döndürür."""
        stmt = select(ToolCall).order_by(desc(ToolCall.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_conversation(self, conversation_id: str) -> list[ToolCall]:
        """Belirli bir sohbetteki araç çağrıları."""
        stmt = (
            select(ToolCall)
            .where(ToolCall.conversation_id == conversation_id)
            .order_by(ToolCall.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def stats_since(self, since: datetime) -> dict[str, int]:
        """Belirli tarihten bu yana durum bazlı sayım."""
        stmt = (
            select(ToolCall.status, func.count())
            .where(ToolCall.created_at >= since)
            .group_by(ToolCall.status)
        )
        result = await self.session.execute(stmt)
        return {
            str(row[0].value if hasattr(row[0], "value") else row[0]): int(row[1]) for row in result
        }
