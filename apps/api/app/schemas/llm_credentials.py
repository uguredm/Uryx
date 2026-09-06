"""Bulut LLM anahtarı şemaları — ham anahtar varsayılan GET'te yoktur."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

class LlmCredentialsStatus(BaseModel):
    """Maskelenmiş kimlik bilgisi özeti."""

    configured: bool
    hint: str = ""
    source: Literal["env", "ui", "none"]
    model: str = ""
    enabled: bool = False
    provider: str = "gemini"
    provider_label: str = "Google Gemini"

class LlmCredentialsUpdate(BaseModel):
    """UI'dan gelen anahtar veya model güncellemesi.

    Boş ``api_key`` kayıtlı UI anahtarını siler ve ``.env`` yedeğine döner.
    """

    api_key: str | None = Field(default=None, max_length=1024)
    model: str | None = Field(default=None, max_length=120)

class LlmCredentialsReveal(BaseModel):
    """Tam anahtar — yalnızca açıkça istenen reveal uçunda."""

    api_key: str
    source: Literal["env", "ui", "none"]
