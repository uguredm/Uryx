"""Uzun süreli hafıza repository'si."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, or_, select, update

from app.db.models import Memory, MemoryCategory, utcnow
from app.db.repositories.base import BaseRepository

class MemoryRepository(BaseRepository[Memory]):
    """Hafıza kayıtları."""

    model = Memory

    async def create(
        self,
        content: str,
        *,
        category: MemoryCategory = MemoryCategory.OTHER,
        importance: float = 0.5,
        source: str = "auto",
        source_conversation_id: str | None = None,
        tags: list[str] | None = None,
        pinned: bool = False,
    ) -> Memory:
        """Yeni hafıza kaydı oluşturur."""
        return await self.add(
            Memory(
                content=content.strip(),
                category=category,
                importance=max(0.0, min(1.0, importance)),
                source=source,
                source_conversation_id=source_conversation_id,
                tags=tags or [],
                pinned=pinned,
            )
        )

    async def list_active(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        category: MemoryCategory | None = None,
        query: str | None = None,
    ) -> list[Memory]:
        """Aktif hafıza kayıtlarını (sabitlenmişler önce) döndürür."""
        stmt = select(Memory).where(Memory.active.is_(True))
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if query:
            stmt = stmt.where(func.lower(Memory.content).like(f"%{query.lower()}%"))
        stmt = (
            stmt.order_by(desc(Memory.pinned), desc(Memory.importance), desc(Memory.updated_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_pinned(self, limit: int = 20) -> list[Memory]:
        """Sabitlenmiş kayıtlar — her istekte prompt'a eklenir."""
        stmt = (
            select(Memory)
            .where(Memory.active.is_(True), Memory.pinned.is_(True))
            .order_by(desc(Memory.importance))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_core(
        self, *, limit: int = 2, min_importance: float = 0.8
    ) -> list[Memory]:
        """Letta çekirdek bellek: yüksek önemli kayıtlar her turda yer kaplar."""
        if limit <= 0:
            return []
        stmt = (
            select(Memory)
            .where(Memory.active.is_(True), Memory.importance >= min_importance)
            .order_by(desc(Memory.pinned), desc(Memory.importance), desc(Memory.updated_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_many(self, ids: list[str]) -> list[Memory]:
        """Verilen kimliklere sahip aktif kayıtları döndürür."""
        if not ids:
            return []
        stmt = select(Memory).where(Memory.id.in_(ids), Memory.active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def sparse_search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        """Anahtar kelime araması — Mem0 BM25 ayağının taşınabilir karşılığı."""
        terms = [t for t in query.lower().split() if len(t) > 2][:8]
        if not terms:
            return []
        clauses = [func.lower(Memory.content).like(f"%{term}%") for term in terms]
        stmt = (
            select(Memory.id, Memory.content)
            .where(Memory.active.is_(True), or_(*clauses))
            .limit(limit * 3)
        )
        rows = (await self.session.execute(stmt)).all()
        scored: list[tuple[str, float]] = []
        for memory_id, content in rows:
            lowered = content.lower()
            hits = sum(lowered.count(term) for term in terms)
            matched = sum(1 for term in terms if term in lowered)
            score = (matched / len(terms)) * 0.7 + min(hits / 8.0, 1.0) * 0.3
            scored.append((str(memory_id), score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def find_similar_text(self, content: str, threshold: int = 40) -> Memory | None:
        """Yakın içerikli mevcut bir kaydı bulur (yinelenmeyi önlemek için).

        Vektör benzerliği Qdrant'ta yapılır; bu metot ucuz bir ön-kontroldür:
        ilk ``threshold`` karakteri aynı olan aktif bir kayıt varsa döndürür.
        """
        prefix = content.strip()[:threshold].lower()
        if not prefix:
            return None
        stmt = select(Memory).where(
            Memory.active.is_(True), func.lower(Memory.content).like(f"{prefix}%")
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def mark_used(self, ids: list[str]) -> None:
        """Kullanım sayaçlarını artırır."""
        if not ids:
            return
        await self.session.execute(
            update(Memory)
            .where(Memory.id.in_(ids))
            .values(use_count=Memory.use_count + 1, last_used_at=utcnow())
        )

    async def set_pinned(self, memory_id: str, pinned: bool) -> None:
        """Kaydı sabitler / sabiti kaldırır."""
        await self.session.execute(
            update(Memory).where(Memory.id == memory_id).values(pinned=pinned)
        )

    async def deactivate(self, memory_id: str) -> None:
        """Kaydı yumuşak siler."""
        await self.session.execute(
            update(Memory).where(Memory.id == memory_id).values(active=False)
        )

    async def stats(self) -> dict[str, Any]:
        """Kategori bazlı özet istatistik."""
        stmt = (
            select(Memory.category, func.count())
            .where(Memory.active.is_(True))
            .group_by(Memory.category)
        )
        rows = (await self.session.execute(stmt)).all()
        by_category = {str(r[0].value if hasattr(r[0], "value") else r[0]): int(r[1]) for r in rows}
        total = sum(by_category.values())
        pinned = await self.count(active=True, pinned=True)
        return {"total": total, "pinned": pinned, "by_category": by_category}
