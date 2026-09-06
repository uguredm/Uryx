"""Sunucu tarafı kullanıcı ayarları repository'si."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting

class SettingsRepository:
    """Anahtar/değer tabanlı ayar deposu."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> dict[str, Any] | None:
        """Tek bir ayarı döndürür."""
        entity = await self.session.get(AppSetting, key)
        return dict(entity.value) if entity else None

    async def get_all(self) -> dict[str, Any]:
        """Tüm ayarları sözlük olarak döndürür."""
        rows = (await self.session.execute(select(AppSetting))).scalars().all()
        return {row.key: row.value for row in rows}

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Ayarı ekler veya günceller."""
        entity = await self.session.get(AppSetting, key)
        if entity is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            entity.value = value
        await self.session.flush()

    async def set_many(self, values: dict[str, Any]) -> None:
        """Birden fazla ayarı topluca yazar."""
        for key, value in values.items():
            payload = value if isinstance(value, dict) else {"value": value}
            await self.set(key, payload)

    async def delete(self, key: str) -> bool:
        """Ayarı siler."""
        entity = await self.session.get(AppSetting, key)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True
