"""TTS sağlayıcı arayüzü ve Piper mikroservis istemcisi.

``TTSProvider`` protokolü sayesinde ileride XTTS-v2 gibi başka bir motor
eklendiğinde çağıran kodda değişiklik gerekmez (bkz. ARCHITECTURE.md).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.errors import TTSUnavailableError
from app.core.logging import get_logger
from app.schemas.speech import VoiceInfo

logger = get_logger(__name__)

SENTENCE_END = re.compile(r"(?<=[.!?…:;])\s+|\n{2,}")
MIN_SENTENCE_CHARS = 25
FIRST_SENTENCE_CHARS = 6
MAX_SENTENCE_CHARS = 400

@runtime_checkable
class TTSProvider(Protocol):
    """Seslendirme sağlayıcısı sözleşmesi."""

    async def health(self) -> bool:
        """Servis ayakta mı?"""
        ...

    async def voices(self) -> list[VoiceInfo]:
        """Kullanılabilir sesler."""
        ...

    async def synthesize(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> bytes:
        """Metni WAV baytlarına çevirir."""
        ...

class PiperTTSClient:
    """``services/tts`` mikroservisinin HTTP istemcisi."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.tts_url.rstrip("/"),
            timeout=httpx.Timeout(settings.tts_timeout, connect=5.0),
        )

    async def aclose(self) -> None:
        """İstemciyi kapatır."""
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> bool:
        """Servis ayakta mı?"""
        try:
            response = await self._client.get("/health", timeout=4.0)
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def status(self) -> dict[str, Any]:
        """Servis durumu ve aktif ses."""
        try:
            response = await self._client.get("/status", timeout=5.0)
            response.raise_for_status()
            return dict(response.json())
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return {"available": False, "detail": str(exc)}

    async def voices(self) -> list[VoiceInfo]:
        """Kurulu ve kurulabilir sesleri listeler."""
        try:
            response = await self._client.get("/voices", timeout=8.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, OSError, ValueError):
            return []
        return [
            VoiceInfo(
                id=str(v.get("id", "")),
                name=str(v.get("name", v.get("id", ""))),
                language=str(v.get("language", "tr")),
                quality=str(v.get("quality", "medium")),
                installed=bool(v.get("installed", False)),
            )
            for v in (payload.get("voices") or [])
        ]

    async def synthesize(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> bytes:
        """Metni WAV baytlarına çevirir.

        Raises:
            TTSUnavailableError: Servis kapalıysa veya ses üretilemezse.
        """
        text = text.strip()
        if not text:
            return b""

        payload = {
            "text": text[:5000],
            "voice": voice or self._settings.tts_voice,
            "speed": speed if speed is not None else self._settings.tts_speed,
        }
        try:
            response = await self._client.post("/synthesize", json=payload)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            logger.warning("tts_http_error", status=exc.response.status_code, detail=detail)
            raise TTSUnavailableError(
                f"Seslendirme başarısız (HTTP {exc.response.status_code}).",
                details={"detail": detail},
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise TTSUnavailableError() from exc

class SentenceBuffer:
    """Akan metni seslendirilebilir cümlelere böler.

    LLM token üretirken cümle tamamlandıkça TTS'e gönderilir; böylece cevabın
    tamamı beklenmeden ses üretimi başlar.
    """

    def __init__(
        self,
        min_chars: int = MIN_SENTENCE_CHARS,
        max_chars: int = MAX_SENTENCE_CHARS,
        first_min_chars: int = FIRST_SENTENCE_CHARS,
    ) -> None:
        self._buffer = ""
        self._min = min_chars
        self._max = max_chars
        self._first_min = first_min_chars
        self._first = True

    def feed(self, text: str) -> list[str]:
        """Yeni metin ekler ve hazır cümleleri döndürür."""
        self._buffer += text
        ready: list[str] = []

        while True:
            min_needed = self._first_min if self._first else self._min
            match = SENTENCE_END.search(self._buffer)
            if match and match.end() >= min_needed:
                sentence = self._buffer[: match.start()].strip()
                self._buffer = self._buffer[match.end() :]
                if sentence:
                    ready.append(sentence)
                    self._first = False
                continue
            if len(self._buffer) > self._max:
                cut = self._buffer.rfind(" ", 0, self._max)
                cut = cut if cut > min_needed else self._max
                sentence = self._buffer[:cut].strip()
                self._buffer = self._buffer[cut:].lstrip()
                if sentence:
                    ready.append(sentence)
                    self._first = False
                continue
            break
        return [_clean_for_speech(s) for s in ready if _clean_for_speech(s)]

    def flush(self) -> str | None:
        """Kalan metni döndürür."""
        remaining, self._buffer = self._buffer.strip(), ""
        cleaned = _clean_for_speech(remaining)
        return cleaned or None

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_SOURCE_LINE = re.compile(
    r"^\s*(?:[*_-]*\s*)?(?:kaynak(?:lar)?|sources?|görsel|fotoğraf)\s*:.*$",
    re.IGNORECASE | re.MULTILINE,
)
_LIST_LINE = re.compile(r"^\s*(?:[-+*]\s+|\d+[.)]\s+).*$", re.MULTILINE)
_MD_EMPHASIS = re.compile(r"[*_#>]{1,3}")
_MULTI_SPACE = re.compile(r"\s{2,}")

def _clean_for_speech(text: str) -> str:
    """Markdown işaretlerini seslendirmeye uygun biçimde temizler."""
    if not text:
        return ""
    cleaned = _CODE_BLOCK.sub(" ", text)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    cleaned = _MD_IMAGE.sub(" ", cleaned)
    cleaned = _MD_LINK.sub(r"\1", cleaned)
    cleaned = _SOURCE_LINE.sub(" ", cleaned)
    cleaned = _LIST_LINE.sub(" ", cleaned)
    cleaned = _URL.sub(" ", cleaned)
    cleaned = _MD_EMPHASIS.sub("", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    return cleaned.strip()

async def stream_sentences(source: AsyncIterator[str]) -> AsyncIterator[str]:
    """Token akışını cümle akışına çevirir (yardımcı)."""
    buffer = SentenceBuffer()
    async for piece in source:
        for sentence in buffer.feed(piece):
            yield sentence
    tail = buffer.flush()
    if tail:
        yield tail
