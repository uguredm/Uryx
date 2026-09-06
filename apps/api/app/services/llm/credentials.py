"""Çalışma anında bulut LLM kimlik bilgisi yükleme / maskeleme / uygulama."""

from __future__ import annotations

from typing import Any, Literal

from app.core.container import Container
from app.core.errors import DatabaseUnavailableError
from app.core.logging import get_logger
from app.db.repositories.settings import SettingsRepository
from app.services.llm.providers import detect_cloud_provider, label_for, provider_by_id

logger = get_logger(__name__)

CREDENTIALS_KEY = "llm_credentials"
Source = Literal["env", "ui", "none"]

def hint_for(api_key: str) -> str:
    """Son dört karakter; kısa anahtarda tümü."""
    key = api_key.strip()
    if not key:
        return ""
    return key[-4:] if len(key) >= 4 else key

class LlmCredentialsService:
    """Postgres ``app_settings`` + canlı HybridLLMClient."""

    def __init__(self, container: Container) -> None:
        self._container = container

    async def status(self) -> dict[str, Any]:
        """Maskeli özet; ham anahtar içermez."""
        stored = await self._load_stored()
        source, key = self._effective(stored)
        settings = self._container.settings
        provider_id = str((stored or {}).get("provider") or settings.cloud_provider or "gemini")
        return {
            "configured": bool(key),
            "hint": hint_for(key),
            "source": source,
            "model": str((stored or {}).get("model") or settings.gemini_model),
            "enabled": bool(settings.gemini_enabled and key),
            "provider": provider_id,
            "provider_label": label_for(provider_id),
        }

    async def reveal(self) -> dict[str, Any]:
        """Tam anahtarı bir kez döner — router token ister."""
        stored = await self._load_stored()
        source, key = self._effective(stored)
        return {"api_key": key, "source": source}

    async def save(self, api_key: str | None, model: str | None) -> dict[str, Any]:
        """UI anahtarını kaydeder veya boşsa siler; istemciyi canlı yeniler."""
        stored = await self._load_stored() or {}
        if api_key is not None and not api_key.strip():
            self._require_database()
            await self._delete_stored()
            await self._container.apply_env_gemini()
            if model and model.strip():
                self._container.settings.gemini_model = model.strip()
                await self._container.rebuild_gemini_client()
            logger.info("llm_credentials_cleared")
            return await self.status()

        next_key = api_key.strip() if api_key is not None else str(stored.get("api_key") or "")
        next_model = model.strip() if model is not None else str(stored.get("model") or "")
        if api_key is None and model is None:
            return await self.status()

        resolved = detect_cloud_provider(next_key, next_model) if next_key else provider_by_id(
            str(stored.get("provider") or "gemini")
        )
        if next_key and not next_model:
            next_model = resolved.default_model
        payload = {
            "api_key": next_key,
            "model": next_model,
            "provider": resolved.id,
            "url": resolved.url,
        }
        if next_key:
            self._require_database()
            await self._write_stored(payload)
            await self._container.apply_ui_gemini(
                next_key,
                next_model or None,
                provider=resolved.id,
                url=resolved.url,
            )
        elif next_model:
            self._container.settings.gemini_model = next_model
            await self._container.rebuild_gemini_client()
        logger.info(
            "llm_credentials_saved",
            configured=bool(next_key),
            has_model=bool(next_model),
            provider=resolved.id,
        )
        return await self.status()

    def _require_database(self) -> None:
        """Yazma işlemleri için veritabanı zorunlu."""
        if not self._container.database.available:
            raise DatabaseUnavailableError()

    async def _load_stored(self) -> dict[str, Any] | None:
        database = self._container.database
        if not database.available:
            return None
        async with database.session() as session:
            value = await SettingsRepository(session).get(CREDENTIALS_KEY)
        return dict(value) if isinstance(value, dict) else None

    async def _write_stored(self, payload: dict[str, Any]) -> None:
        async with self._container.database.session() as session:
            await SettingsRepository(session).set(CREDENTIALS_KEY, payload)

    async def _delete_stored(self) -> None:
        async with self._container.database.session() as session:
            await SettingsRepository(session).delete(CREDENTIALS_KEY)

    def _effective(self, stored: dict[str, Any] | None) -> tuple[Source, str]:
        ui_key = str((stored or {}).get("api_key") or "").strip()
        if ui_key:
            return "ui", ui_key
        env_key = self._container.env_gemini_api_key.strip()
        if env_key:
            return "env", env_key
        return "none", ""
