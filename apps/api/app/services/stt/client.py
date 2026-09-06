"""STT sağlayıcı arayüzü ve Faster-Whisper mikroservis istemcisi."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.errors import STTUnavailableError, ValidationError
from app.core.logging import get_logger
from app.schemas.speech import STTStatus, TranscriptionResult, TranscriptionSegment
from app.services.stt.quality import (
    is_backchannel,
    is_low_quality_segment,
    whisper_decode_hints,
)

logger = get_logger(__name__)

_LEAKED_PROMPT = re.compile(
    r"Türkçe konuşma kaydı\.?\s*Noktalama işaretlerini ve büyük "
    r"harf(?:leri|lerini) doğru kullan\.?",
    re.IGNORECASE,
)
_HALLUCINATION_ONLY = {
    "ayakta mısın altyazı m k",
    "türkçe konuşma kaydı",
    "noktalama işaretlerini ve büyük harfleri doğru kullan",
    "noktalama işaretlerini ve büyük harflerini doğru kullan",
    "izlediğiniz için teşekkür ederim",
    "abone olmayı unutmayın",
    "bir sonraki videoda görüşmek üzere",
    "altyazı",
    "çeviri ve altyazı",
}
_SUBTITLE_SIGNATURE = re.compile(
    r"(?:çeviri\s+ve\s+)?altyaz[ıi]\s*:?[ ]*"
    r"(?:[A-ZÇĞİÖŞÜ]\s*\.\s*){1,5}[A-ZÇĞİÖŞÜ]?\.?$",
    re.IGNORECASE,
)

def sanitize_transcription(value: str) -> str:
    """Whisper prompt sızıntısını ve yaygın altyazı imzası halüsinasyonlarını temizler."""
    text = " ".join(value.split())
    original_folded = text.replace("İ", "i").replace("I", "ı").casefold()
    original_normalized = re.sub(r"[^\wçğıöşü]+", " ", original_folded).strip()
    if original_normalized in _HALLUCINATION_ONLY:
        return ""

    text = _LEAKED_PROMPT.sub("", text)
    text = _SUBTITLE_SIGNATURE.sub("", text).strip()
    folded = text.replace("İ", "i").replace("I", "ı").casefold()
    normalized = re.sub(r"[^\wçğıöşü]+", " ", folded).strip()
    return "" if normalized in _HALLUCINATION_ONLY else text

def _opt_float(value: Any) -> float | None:
    """JSON metrikini float'a çevirir."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

@runtime_checkable
class STTProvider(Protocol):
    """Konuşma tanıma sağlayıcısı sözleşmesi."""

    async def health(self) -> bool:
        """Servis ayakta mı?"""
        ...

    async def status(self) -> STTStatus:
        """Model ve cihaz bilgisi."""
        ...

    async def transcribe(
        self,
        audio: bytes,
        filename: str,
        *,
        language: str | None = None,
        vad_filter: bool = False,
    ) -> TranscriptionResult:
        """Ses verisini metne çevirir."""
        ...

    async def reload(self, model: str) -> STTStatus:
        """Yüklü Whisper modelini değiştirir (konteyner yeniden yaratılmaz)."""
        ...

class WhisperClient:
    """``services/whisper`` mikroservisinin HTTP istemcisi."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.whisper_url.rstrip("/"),
            timeout=httpx.Timeout(settings.whisper_timeout, connect=5.0),
        )
        self._status_cache: STTStatus | None = None

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

    async def status(self) -> STTStatus:
        """Model, cihaz ve dil bilgisini döndürür."""
        try:
            response = await self._client.get("/status", timeout=5.0)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            self._status_cache = STTStatus(
                available=bool(data.get("model_loaded", False)),
                model=str(data.get("model", "")),
                device=str(data.get("device", "")),
                language=str(data.get("language", self._settings.whisper_language)),
                detail=data.get("detail"),
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            self._status_cache = STTStatus(
                available=False,
                model=self._settings.whisper_model,
                language=self._settings.whisper_language,
                detail=f"Whisper servisine ulaşılamadı: {exc}",
            )
        return self._status_cache

    async def reload(self, model: str) -> STTStatus:
        """Whisper modelini POST /reload ile değiştirir; konteyner durmaz."""
        name = model.strip()
        if not name:
            raise ValidationError("Whisper modeli boş.")
        try:
            response = await self._client.post(
                "/reload",
                json={"model": name},
                timeout=httpx.Timeout(self._settings.whisper_timeout, connect=5.0),
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            logger.error("whisper_reload_http_error", status=exc.response.status_code, detail=detail)
            if exc.response.status_code in {400, 422}:
                raise ValidationError(
                    "Whisper modeli geçersiz veya yüklenemedi.",
                    details={"detail": detail},
                ) from exc
            raise STTUnavailableError(
                f"Whisper yeniden yükleme başarısız (HTTP {exc.response.status_code}).",
                details={"detail": detail},
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise STTUnavailableError() from exc
        except ValueError as exc:
            raise STTUnavailableError("Whisper servisi geçersiz cevap döndürdü.") from exc

        self._status_cache = STTStatus(
            available=bool(data.get("model_loaded", False)),
            model=str(data.get("model", name)),
            device=str(data.get("device", "")),
            language=str(data.get("language", self._settings.whisper_language)),
            detail=data.get("detail"),
        )
        return self._status_cache

    async def transcribe(
        self,
        audio: bytes,
        filename: str = "audio.webm",
        *,
        language: str | None = None,
        vad_filter: bool = False,
    ) -> TranscriptionResult:
        """Ses verisini Türkçe metne çevirir.

        Raises:
            STTUnavailableError: Servis kapalıysa veya hata dönerse.
        """
        if not audio:
            raise STTUnavailableError("Boş ses verisi gönderildi.")

        files = {"file": (filename, audio, "application/octet-stream")}
        data = {
            "language": language or self._settings.whisper_language,
            "vad_filter": str(vad_filter).lower(),
            **whisper_decode_hints(),
        }

        try:
            response = await self._client.post("/transcribe", files=files, data=data)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            logger.error("whisper_http_error", status=exc.response.status_code, detail=detail)
            raise STTUnavailableError(
                f"Transkripsiyon başarısız (HTTP {exc.response.status_code}).",
                details={"detail": detail},
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise STTUnavailableError() from exc
        except ValueError as exc:
            raise STTUnavailableError("Whisper servisi geçersiz cevap döndürdü.") from exc

        segments: list[TranscriptionSegment] = []
        for raw in payload.get("segments") or []:
            if is_low_quality_segment(
                no_speech_prob=_opt_float(raw.get("no_speech_prob")),
                avg_logprob=_opt_float(raw.get("avg_logprob")),
                compression_ratio=_opt_float(raw.get("compression_ratio")),
            ):
                continue
            cleaned = sanitize_transcription(str(raw.get("text", "")))
            if not cleaned:
                continue
            segments.append(
                TranscriptionSegment(
                    start=float(raw.get("start", 0.0)),
                    end=float(raw.get("end", 0.0)),
                    text=cleaned,
                )
            )
        text = sanitize_transcription(str(payload.get("text", "")))
        if len(segments) > 1:
            spoken = [
                item
                for item in segments
                if not (is_backchannel(item.text) and (item.end - item.start) < 0.5)
            ]
            if spoken:
                segments = spoken
        if segments:
            text = " ".join(item.text for item in segments).strip()

        return TranscriptionResult(
            text=text,
            language=str(payload.get("language", data["language"])),
            duration=float(payload.get("duration", 0.0)),
            segments=segments,
            model=str(payload.get("model", "")),
            device=str(payload.get("device", "")),
        )

    async def transcribe_stream(
        self,
        chunks: list[bytes],
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Whisper ``/ws/transcribe`` üzerinden parça parça çevirir."""
        from app.services.stt.stream import parse_stream_event, stream_control

        if not chunks or not any(chunks):
            raise STTUnavailableError("Boş ses verisi gönderildi.")

        base = self._settings.whisper_url.rstrip("/")
        uri = base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        uri = f"{uri}/ws/transcribe"
        last = ""
        lang = language or self._settings.whisper_language
        hints = whisper_decode_hints()
        try:
            import websockets

            async with websockets.connect(uri, open_timeout=5, close_timeout=2) as socket:
                await socket.send(
                    json.dumps(stream_control("start", language=lang, **hints))
                )
                for chunk in chunks:
                    if chunk:
                        await socket.send(chunk)
                await socket.send(
                    json.dumps(stream_control("end", language=lang, **hints))
                )
                async for raw in socket:
                    if isinstance(raw, bytes):
                        continue
                    kind, text = parse_stream_event(json.loads(raw))
                    if kind == "error":
                        raise STTUnavailableError(text or "Whisper akışı hata verdi.")
                    if text:
                        last = text
                    if kind == "final":
                        break
        except STTUnavailableError:
            raise
        except Exception as exc:
            raise STTUnavailableError() from exc

        return TranscriptionResult(
            text=sanitize_transcription(last),
            language=language or self._settings.whisper_language,
        )
