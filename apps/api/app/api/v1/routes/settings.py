"""Sunucu tarafında saklanan kullanıcı ayarları.

Masaüstü uygulamasının kendi yerel ayarları (electron-store) ayrıdır; buradaki
ayarlar birden fazla istemci arasında paylaşılabilen sunucu tarafı tercihlerdir.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import DatabaseDep
from app.core.errors import NotFoundError, ValidationError
from app.core.security import require_token
from app.db.repositories.settings import SettingsRepository
from app.schemas.common import OkResponse

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_token)])

ALLOWED_KEYS = {
    "chat_defaults",
    "tts_preferences",
    "stt_preferences",
    "rag_preferences",
    "memory_preferences",
    "ui_preferences",
}

SECRET_KEYS = frozenset({"llm_credentials"})

def _reject_secret(key: str) -> None:
    """Sır anahtarlarını genel ayar uçlarından gizler."""
    if key in SECRET_KEYS:
        raise NotFoundError(f"'{key}' ayarı bulunamadı.")

@router.get("", summary="Tüm ayarları getir")
async def get_settings_all(database: DatabaseDep) -> dict[str, Any]:
    """Kaydedilmiş tüm sunucu ayarlarını döndürür."""
    async with database.session() as session:
        values = await SettingsRepository(session).get_all()
    for key in SECRET_KEYS:
        values.pop(key, None)
    return values

@router.get("/{key}", summary="Tek ayarı getir")
async def get_setting(key: str, database: DatabaseDep) -> dict[str, Any]:
    """Belirli bir ayarı döndürür."""
    _reject_secret(key)
    async with database.session() as session:
        value = await SettingsRepository(session).get(key)
    if value is None:
        raise NotFoundError(f"'{key}' ayarı bulunamadı.")
    return value

@router.put("/{key}", response_model=OkResponse, summary="Ayarı kaydet")
async def put_setting(key: str, payload: dict[str, Any], database: DatabaseDep) -> OkResponse:
    """Ayarı ekler veya günceller.

    Raises:
        ValidationError: Anahtar izin listesinde değilse.
    """
    if key not in ALLOWED_KEYS:
        raise ValidationError(
            f"'{key}' yazılabilir bir ayar anahtarı değil.",
            details={"allowed": sorted(ALLOWED_KEYS)},
        )
    async with database.session() as session:
        await SettingsRepository(session).set(key, payload)
    return OkResponse(message="Ayar kaydedildi.")

@router.delete("/{key}", response_model=OkResponse, summary="Ayarı sil")
async def delete_setting(key: str, database: DatabaseDep) -> OkResponse:
    """Ayarı siler."""
    _reject_secret(key)
    async with database.session() as session:
        deleted = await SettingsRepository(session).delete(key)
    if not deleted:
        raise NotFoundError(f"'{key}' ayarı bulunamadı.")
    return OkResponse(message="Ayar silindi.")
