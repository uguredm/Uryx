"""Repository Pattern taban sınıfı.

Servis katmanı ORM'i doğrudan görmez; yalnızca repository arayüzleriyle konuşur.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base

ModelT = TypeVar("ModelT", bound=Base)

class BaseRepository(Generic[ModelT]):
    """Ortak CRUD işlemleri."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: str) -> ModelT | None:
        """Kimliğe göre tek kayıt döndürür."""
        return await self.session.get(self.model, entity_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: Any | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        """Filtrelenmiş kayıt listesi döndürür."""
        stmt = select(self.model)
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count(self, **filters: Any) -> int:
        """Filtreye uyan kayıt sayısı."""
        stmt = select(func.count()).select_from(self.model)
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def add(self, entity: ModelT) -> ModelT:
        """Yeni kayıt ekler ve flush eder."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelT, **values: Any) -> ModelT:
        """Kaydın alanlarını günceller."""
        for field, value in values.items():
            if value is not None and hasattr(entity, field):
                setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: str) -> bool:
        """Kaydı siler; silinen satır sayısı 0'dan büyükse ``True``."""
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        return bool(result.rowcount)
