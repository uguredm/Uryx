"""Piper TTS mikroservisi (CPU).

Türkçe sesli cevap üretir. Ses modeli ilk açılışta Hugging Face'ten indirilir ve
kalıcı volume'de saklanır. Piper veya ses modeli kullanılamazsa servis ayakta
kalır; ``/synthesize`` açıklayıcı bir 503 döndürür ve masaüstü uygulaması sesli
cevabı otomatik kapatır.

Provider arayüzü: yeni bir motor (ör. XTTS-v2) eklemek için ``TTSEngine``
protokolünü uygulayan bir sınıf yazıp ``ENGINE`` değişkenini değiştirmek yeterlidir.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time
import wave
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

import edge as edge_tts
import voices as voice_catalog

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s [tts] %(message)s",
)
logger = logging.getLogger("tts")

VOICE_DIR = Path(os.environ.get("PIPER_VOICE_DIR", "/voices"))
REQUESTED_VOICE = os.environ.get("TTS_VOICE", voice_catalog.DEFAULT_VOICE)
DEFAULT_SPEED = float(os.environ.get("TTS_SPEED", "1.0"))
MAX_TEXT_CHARS = 5000

class TTSEngine(Protocol):
    """Seslendirme motoru sözleşmesi."""

    def synthesize(self, text: str, *, speed: float) -> bytes:
        """Metni WAV baytlarına çevirir."""
        ...

class PiperEngine:
    """Piper ONNX motoru."""

    def __init__(self, voice_id: str, model_path: Path, config_path: Path) -> None:
        from piper import PiperVoice

        self.voice_id = voice_id
        self._voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        self.sample_rate = int(self._voice.config.sample_rate)

    def synthesize(self, text: str, *, speed: float) -> bytes:
        """Metni WAV baytlarına çevirir.

        ``length_scale`` konuşma hızının tersidir: 1/hız.
        """
        length_scale = max(0.4, min(1 / max(speed, 0.1), 2.5))
        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            try:
                self._voice.synthesize(text, wav_file, length_scale=length_scale)
            except TypeError:

                self._voice.synthesize(text, wav_file)

        return buffer.getvalue()

class EngineState:
    """Motor durumu."""

    def __init__(self) -> None:
        self.engine: TTSEngine | None = None
        self.engines: dict[str, TTSEngine] = {}
        self.voice_id: str | None = None
        self.error: str | None = None
        self.lock = asyncio.Lock()
        self.loading = False

state = EngineState()

async def load_engine(voice_id: str | None = None) -> None:
    """İstenen sesi hazırlar ve motoru yükler."""
    target = voice_id or REQUESTED_VOICE
    async with state.lock:
        if state.engine is not None and state.voice_id == target:
            return
        state.loading = True
        try:
            cached = state.engines.get(target)
            if cached is not None:
                state.engine = cached
                state.voice_id = target
                state.error = None
                return
            resolved = await voice_catalog.ensure_voice(VOICE_DIR, target)
            if resolved is None:
                state.engine = None
                state.voice_id = None
                state.error = (
                    "Türkçe ses modeli indirilemedi. İnternet bağlantısını kontrol edin "
                    "veya .onnx dosyasını elle 'uryx-piper-voices' volume'üne kopyalayın."
                )
                logger.error(state.error)
                return

            model_path, config_path = voice_catalog.local_paths(VOICE_DIR, resolved)
            state.engine = await asyncio.to_thread(PiperEngine, resolved, model_path, config_path)
            state.engines[resolved] = state.engine
            state.voice_id = resolved
            state.error = None
            logger.info("Piper hazır: %s", resolved)
        except Exception as exc:  # noqa: BLE001 - servis ayakta kalmalı
            state.engine = None
            state.error = f"Piper motoru yüklenemedi: {exc}"
            logger.error(state.error)
        finally:
            state.loading = False

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Servis açılırken sesi arka planda hazırlar."""
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(load_engine())
    yield
    task.cancel()

app = FastAPI(title="Uryx TTS (Piper)", version="0.1.0", lifespan=lifespan)

class SynthesizeRequest(BaseModel):
    """Seslendirme isteği."""

    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    voice: str | None = None
    speed: float = Field(default=DEFAULT_SPEED, ge=0.5, le=2.0)
    auto_language: bool = True

@app.get("/health")
async def health() -> dict[str, Any]:
    """Konteyner healthcheck'i (ses hazır olmasa da 200 döner)."""
    return {
        "status": "ok",
        "engine_ready": state.engine is not None,
        "voice": state.voice_id,
    }

@app.get("/status")
async def status() -> dict[str, Any]:
    """Motor durumu ve aktif ses."""
    return {
        "available": state.engine is not None,
        "loading": state.loading,
        "voice": state.voice_id,
        "requested_voice": REQUESTED_VOICE,
        "detail": state.error,
        "installed": voice_catalog.installed_voices(VOICE_DIR),
    }

@app.get("/voices")
async def list_voices() -> dict[str, Any]:
    """Katalogdaki ve kurulu sesleri listeler."""
    return {"voices": voice_catalog.catalog_entries(VOICE_DIR), "active": state.voice_id}

@app.post("/voices/{voice_id}/download")
async def download_voice(voice_id: str) -> dict[str, Any]:
    """Bir sesi indirir ve aktif hâle getirir."""
    if voice_id not in voice_catalog.CATALOG:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen ses: {voice_id}")
    ok = await voice_catalog.download_voice(VOICE_DIR, voice_id)
    if not ok:
        raise HTTPException(status_code=502, detail="Ses indirilemedi.")
    await load_engine(voice_id)
    return {"ok": True, "voice": state.voice_id}

@app.post("/synthesize")
async def synthesize(payload: SynthesizeRequest) -> Response:
    """Metni WAV sesine çevirir."""
    requested_voice = payload.voice
    if (
        payload.auto_language
        and _looks_english(payload.text)
        and not edge_tts.is_edge_voice(requested_voice)
    ):
        requested_voice = "en_US-lessac-medium"

    if edge_tts.is_edge_voice(requested_voice):
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Metin boş.")
        try:
            started = time.perf_counter()
            audio = await edge_tts.synthesize_edge(
                text[:MAX_TEXT_CHARS],
                voice=requested_voice or "tr-TR-AhmetNeural",
                speed=payload.speed,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            return Response(
                content=audio,
                media_type="audio/wav",
                headers={
                    "Cache-Control": "no-store",
                    "X-Uryx-Voice": requested_voice or "",
                    "X-Uryx-Elapsed-Ms": str(elapsed),
                    "X-Uryx-Engine": "edge-neural",
                },
            )
        except Exception as exc:  # noqa: BLE001 - Piper yedeğine düş
            logger.warning("Edge TTS başarısız, Piper yedeği: %s", exc)
            requested_voice = edge_tts.piper_fallback_voice(requested_voice)

    if requested_voice and requested_voice != state.voice_id:
        await load_engine(requested_voice)
    elif state.engine is None:
        await load_engine()

    if state.engine is None:
        raise HTTPException(
            status_code=503,
            detail=state.error or "Seslendirme motoru hazır değil.",
        )

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Metin boş.")

    started = time.perf_counter()
    try:
        audio = await asyncio.to_thread(
            state.engine.synthesize, text[:MAX_TEXT_CHARS], speed=payload.speed
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Seslendirme hatası: %s", exc)
        raise HTTPException(status_code=500, detail=f"Seslendirme hatası: {exc}") from exc

    elapsed = int((time.perf_counter() - started) * 1000)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Uryx-Voice": state.voice_id or "",
            "X-Uryx-Elapsed-Ms": str(elapsed),
        },
    )

_WORDS = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü']+")
_ENGLISH_HINTS = {
    "the", "and", "with", "this", "that", "from", "for", "your", "you", "is",
    "are", "was", "were", "how", "what", "when", "where", "latest", "version",
}
_TURKISH_HINTS = {
    "ve", "ile", "bu", "şu", "bir", "için", "sen", "siz", "nasıl", "nedir",
    "son", "sürüm", "olarak", "var", "yok", "olan", "gibi", "daha",
}

def _looks_english(text: str) -> bool:
    """Belirgin biçimde İngilizce olan cümleleri Türkçe Piper'a göndermemeyi sağlar."""
    words = [word.lower() for word in _WORDS.findall(text)]
    if len(words) < 3:
        return False
    english = sum(word in _ENGLISH_HINTS for word in words)
    turkish = sum(word in _TURKISH_HINTS for word in words)
    has_turkish_chars = bool(re.search(r"[çğıöşüÇĞİÖŞÜ]", text))
    return english >= 2 and english > turkish and not has_turkish_chars
