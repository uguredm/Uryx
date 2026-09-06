"""Faster-Whisper STT mikroservisi.

Türkçe konuşma tanıma için optimize edilmiştir. GPU (CUDA) varsa onu kullanır;
yoksa veya CUDA başlatılamazsa otomatik olarak CPU'ya düşer (int8 quantization).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi import WebSocketDisconnect
from pydantic import BaseModel

from stream import AudioStreamBuffer, parse_stream_config, should_emit_partial

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s [whisper] %(message)s",
)
logger = logging.getLogger("whisper")

MODEL_NAME = os.environ.get("WHISPER_MODEL", "medium")
DEVICE_PREFERENCE = os.environ.get("WHISPER_DEVICE", "auto").lower()
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
DEFAULT_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "tr")
VAD_FILTER = os.environ.get("WHISPER_VAD_FILTER", "true").lower() in {"1", "true", "yes"}

HOTWORDS = "Uryx Whisper Piper Qdrant Docker"
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))
MODEL_DIR = os.environ.get("HF_HOME", "/models")
NO_SPEECH_MAX = float(os.environ.get("WHISPER_NO_SPEECH", "0.65"))
MIN_AVG_LOGPROB = float(os.environ.get("WHISPER_MIN_LOGPROB", "-1.15"))
MAX_COMPRESSION = float(os.environ.get("WHISPER_MAX_COMPRESSION", "2.4"))
SHORT_UTTERANCE_SEC = float(os.environ.get("WHISPER_SHORT_UTTERANCE_SEC", "4"))

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

KNOWN_MODELS = {
    "tiny": 75,
    "base": 145,
    "small": 484,
    "medium": 1530,
    "large-v3": 3090,
    "distil-large-v3": 1510,
}

class ServiceState:
    """Model ve cihaz durumu."""

    def __init__(self) -> None:
        self.model: Any | None = None
        self.device: str = "unknown"
        self.compute_type: str = COMPUTE_TYPE
        self.model_name: str = MODEL_NAME
        self.error: str | None = None
        self.loading: bool = False
        self.lock = asyncio.Lock()

state = ServiceState()

def _resolve_device() -> tuple[str, str]:
    """Kullanılacak cihazı ve compute type'ı belirler."""
    if DEVICE_PREFERENCE == "cpu":
        return "cpu", "int8"
    try:
        import ctranslate2

        cuda_count = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001
        logger.warning("CUDA tespiti başarısız (%s) — CPU kullanılacak", exc)
        return "cpu", "int8"

    if cuda_count > 0:
        return "cuda", COMPUTE_TYPE
    logger.warning("CUDA cihazı bulunamadı — CPU'ya düşülüyor")
    return "cpu", "int8"

def _load_model_sync() -> None:
    """Modeli senkron yükler (thread içinde çağrılır)."""
    from faster_whisper import WhisperModel

    device, compute_type = _resolve_device()
    logger.info(
        "Model yükleniyor: %s (device=%s, compute=%s)", state.model_name, device, compute_type
    )
    try:
        model = WhisperModel(
            state.model_name,
            device=device,
            compute_type=compute_type,
            download_root=MODEL_DIR,
            num_workers=1,
        )
    except Exception as exc:  # noqa: BLE001 - GPU başarısızsa CPU'ya düş
        if device == "cuda":
            logger.warning("CUDA ile yükleme başarısız (%s) — CPU'ya düşülüyor", exc)
            device, compute_type = "cpu", "int8"
            model = WhisperModel(
                state.model_name,
                device=device,
                compute_type=compute_type,
                download_root=MODEL_DIR,
                num_workers=1,
            )
        else:
            raise

    state.model = model
    state.device = device
    state.compute_type = compute_type
    state.error = None
    logger.info("Model hazır: %s @ %s", state.model_name, device)

async def ensure_model() -> None:
    """Model yüklü değilse yükler."""
    if state.model is not None:
        return
    async with state.lock:
        if state.model is not None:
            return
        state.loading = True
        try:
            await asyncio.to_thread(_load_model_sync)
        except Exception as exc:  # noqa: BLE001
            state.error = str(exc)
            logger.error("Model yüklenemedi: %s", exc)
        finally:
            state.loading = False

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Servis açılırken modeli arka planda yüklemeye başlar."""
    Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(ensure_model())
    yield
    task.cancel()

app = FastAPI(title="Uryx Whisper", version="0.1.0", lifespan=lifespan)

class Segment(BaseModel):
    """Transkripsiyon parçası."""

    start: float
    end: float
    text: str
    no_speech_prob: float | None = None
    avg_logprob: float | None = None
    compression_ratio: float | None = None

class TranscriptionResponse(BaseModel):
    """Transkripsiyon cevabı."""

    text: str
    language: str
    duration: float
    segments: list[Segment]
    model: str
    device: str
    elapsed_ms: int

class ReloadRequest(BaseModel):
    """Canlı model değişimi — konteyner yeniden yaratılmaz."""

    model: str

class StatusResponse(BaseModel):
    """Servis durumu."""

    model_loaded: bool
    loading: bool
    model: str
    device: str
    compute_type: str
    language: str
    vad_filter: bool
    detail: str | None = None
    available_models: list[dict[str, Any]]

@app.get("/health")
async def health() -> dict[str, Any]:
    """Konteyner healthcheck'i.

    Model yüklenmeyi beklerken de 200 döner; aksi hâlde konteyner sağlıksız
    sayılır ve compose bağımlılıkları başlamaz.
    """
    return {"status": "ok", "model_loaded": state.model is not None, "device": state.device}

@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """Model, cihaz ve dil bilgisini döndürür."""
    return StatusResponse(
        model_loaded=state.model is not None,
        loading=state.loading,
        model=state.model_name,
        device=state.device,
        compute_type=state.compute_type,
        language=DEFAULT_LANGUAGE,
        vad_filter=VAD_FILTER,
        detail=state.error,
        available_models=[
            {"id": name, "name": name, "size_mb": size, "loaded": name == state.model_name}
            for name, size in KNOWN_MODELS.items()
        ],
    )

@app.post("/reload", response_model=StatusResponse)
async def reload_model(payload: ReloadRequest) -> StatusResponse:
    """Yüklü modeli değiştirir; konteyner ayakta kalır."""
    name = payload.model.strip()
    if name not in KNOWN_MODELS:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen Whisper modeli: {name}")
    async with state.lock:
        if name == state.model_name and state.model is not None and not state.error:
            return await status()
        state.model_name = name
        state.model = None
        state.error = None
        state.loading = True
        try:
            await asyncio.to_thread(_load_model_sync)
        except Exception as exc:  # noqa: BLE001
            state.error = str(exc)
            logger.error("Model yeniden yüklenemedi: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Whisper modeli yüklenemedi: {exc}",
            ) from exc
        finally:
            state.loading = False
    return await status()

@app.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket) -> None:
    """Parça parça ses alır; eşikte partial, flush/end'de final döner."""
    await websocket.accept()
    await ensure_model()
    if state.model is None:
        await websocket.send_json({"type": "error", "text": state.error or "model yok"})
        await websocket.close(code=1013)
        return

    buffer = AudioStreamBuffer()
    language = DEFAULT_LANGUAGE
    hotwords = HOTWORDS
    last_partial = ""
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            raw_bytes = message.get("bytes")
            if raw_bytes:
                if buffer.feed(raw_bytes):
                    text = await _transcribe_buffer(
                        buffer.snapshot(), language, hotwords
                    )
                    buffer.mark_partial()
                    if should_emit_partial(last_partial, text):
                        last_partial = text
                        await websocket.send_json({"type": "partial", "text": text})
                continue
            raw_text = str(message.get("text") or "")
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except ValueError:
                payload = {"type": raw_text}
            cfg_lang, cfg_hot = parse_stream_config(payload)
            if cfg_lang:
                language = cfg_lang
            if "hotwords" in payload or "prefix" in payload:
                hotwords = cfg_hot
            kind = str(payload.get("type") or "")
            if kind not in {"flush", "end"}:
                continue
            audio = buffer.flush()
            text = (
                await _transcribe_buffer(audio, language, hotwords) if audio else ""
            )
            await websocket.send_json({"type": "final", "text": text})
            if kind == "end":
                break
    except WebSocketDisconnect:
        return

async def _transcribe_buffer(
    payload: bytes, language: str, hotwords: str = HOTWORDS
) -> str:
    """Akış tamponunu tek seferde çözer."""
    if not payload:
        return ""
    with tempfile.TemporaryDirectory(prefix="uryx-stt-ws-") as tmpdir:
        source = Path(tmpdir) / "chunk.bin"
        source.write_bytes(payload)
        audio_path = await asyncio.to_thread(_to_wav, source, Path(tmpdir))
        try:
            async with state.lock:
                if state.model is None:
                    return ""
                result = await asyncio.to_thread(
                    _transcribe_sync,
                    str(audio_path),
                    language,
                    True,
                    1,
                    True,
                    hotwords or HOTWORDS,
                )
        except (ValueError, RuntimeError):

            return ""
        return str(result.get("text") or "")

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(default=""),
    vad_filter: bool = Form(default=VAD_FILTER),
    beam_size: int = Form(default=BEAM_SIZE),
    hotwords: str = Form(default=""),
) -> TranscriptionResponse:
    """Ses dosyasını metne çevirir."""
    await ensure_model()
    if state.model is None:
        raise HTTPException(
            status_code=503,
            detail=f"Whisper modeli yüklenemedi: {state.error or 'bilinmeyen hata'}",
        )

    payload = await file.read()
    await file.close()
    if not payload:
        raise HTTPException(status_code=400, detail="Ses verisi boş.")

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="uryx-stt-") as tmpdir:
        source = Path(tmpdir) / f"input{suffix}"
        source.write_bytes(payload)
        audio_path = await asyncio.to_thread(_to_wav, source, Path(tmpdir))
        duration_hint = _wav_duration_sec(audio_path)
        requested_beam = max(1, min(int(beam_size), 10))
        effective_beam = requested_beam
        if 0 < duration_hint <= SHORT_UTTERANCE_SEC and requested_beam > 2:

            effective_beam = 1

        try:
            async with state.lock:
                if state.model is None:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Whisper modeli yüklenemedi: {state.error or 'bilinmeyen hata'}",
                    )
                result = await asyncio.to_thread(
                    _transcribe_sync,
                    str(audio_path),
                    language or DEFAULT_LANGUAGE,
                    bool(vad_filter),
                    effective_beam,
                    duration_hint <= SHORT_UTTERANCE_SEC if duration_hint else False,
                    hotwords or HOTWORDS,
                )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Transkripsiyon hatası: %s", exc)
            raise HTTPException(status_code=500, detail=f"Transkripsiyon hatası: {exc}") from exc

    return TranscriptionResponse(
        **result,
        model=state.model_name,
        device=state.device,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )

def _to_wav(source: Path, workdir: Path) -> Path:
    """Sesi 16 kHz mono WAV'a çevirir.

    Tarayıcıdan gelen WebM/Opus kaydını faster-whisper doğrudan okuyabilir, ancak
    ffmpeg ile normalize etmek Türkçe tanıma doğruluğunu belirgin biçimde artırır.
    ffmpeg yoksa orijinal dosya kullanılır.
    """
    if shutil.which("ffmpeg") is None:
        return source
    target = workdir / "normalized.wav"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(source),
                "-ac", "1", "-ar", "16000", "-f", "wav",
                str(target),
            ],
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return target if target.exists() and target.stat().st_size > 44 else source
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("ffmpeg dönüşümü başarısız (%s) — ham dosya kullanılacak", exc)
        return source

def _wav_duration_sec(path: Path) -> float:
    """WAV süresini saniye olarak okur; diğer biçimlerde 0."""
    if path.suffix.lower() != ".wav":
        return 0.0
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate() or 16000
            return handle.getnframes() / float(rate)
    except (OSError, wave.Error):
        return 0.0

def _segment_is_noise(segment: Any) -> bool:
    """faster-whisper sessizlik/halüsinasyon metrikleri — OpenAI Whisper eşiği."""
    no_speech = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
    avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    compression = float(getattr(segment, "compression_ratio", 0.0) or 0.0)
    if no_speech >= NO_SPEECH_MAX:
        return True
    if avg_logprob < MIN_AVG_LOGPROB:
        return True
    if compression > MAX_COMPRESSION:
        return True
    return False

def _transcribe_sync(
    path: str,
    language: str,
    vad_filter: bool,
    beam_size: int,
    short_clip: bool = False,
    hotwords: str = HOTWORDS,
) -> dict[str, Any]:
    """Senkron transkripsiyon (thread içinde çağrılır)."""
    segments, info = state.model.transcribe(  # type: ignore[union-attr]
        path,
        language=language or None,
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": 500} if vad_filter else None,
        condition_on_previous_text=False,
        without_timestamps=bool(short_clip),
        compression_ratio_threshold=MAX_COMPRESSION,
        log_prob_threshold=MIN_AVG_LOGPROB,
        no_speech_threshold=NO_SPEECH_MAX,
        hotwords=(hotwords or HOTWORDS).strip() or None,
    )

    collected: list[Segment] = []
    parts: list[str] = []
    for segment in segments:
        if _segment_is_noise(segment):
            continue
        text = _sanitize_transcription(segment.text)
        if not text:
            continue
        collected.append(
            Segment(
                start=round(segment.start, 2),
                end=round(segment.end, 2),
                text=text,
                no_speech_prob=_opt_float(getattr(segment, "no_speech_prob", None)),
                avg_logprob=_opt_float(getattr(segment, "avg_logprob", None)),
                compression_ratio=_opt_float(getattr(segment, "compression_ratio", None)),
            )
        )
        parts.append(text)

    return {
        "text": " ".join(parts).strip(),
        "language": getattr(info, "language", language) or language,
        "duration": round(float(getattr(info, "duration", 0.0)), 2),
        "segments": collected,
    }

def _sanitize_transcription(value: str) -> str:
    """Sessizlikte üretilen yaygın altyazı/prompt halüsinasyonlarını temizler."""
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
    """Metrik alanını float'a çevirir; yoksa None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
