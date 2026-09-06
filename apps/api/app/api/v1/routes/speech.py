"""STT ve TTS endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.api.deps import SettingsDep, STTDep, TTSDep
from app.core.errors import ValidationError
from app.core.security import require_token
from app.schemas.speech import (
    STTReloadRequest,
    STTStatus,
    SynthesizeRequest,
    TranscriptionResult,
    VoiceListResponse,
)

router = APIRouter(prefix="/speech", tags=["speech"], dependencies=[Depends(require_token)])

MAX_AUDIO_BYTES = 25 * 1024 * 1024

@router.get("/stt/status", response_model=STTStatus, summary="Whisper durumu")
async def stt_status(stt: STTDep) -> STTStatus:
    """Yüklü Whisper modeli ve çalıştığı cihaz."""
    return await stt.status()

@router.post("/stt/reload", response_model=STTStatus, summary="Whisper modelini yeniden yükle")
async def stt_reload(payload: STTReloadRequest, stt: STTDep) -> STTStatus:
    """Store/Ayarlar değişince model POST ile değişir; konteyner yeniden yaratılmaz."""
    return await stt.reload(payload.model.strip())

@router.post("/stt/transcribe", response_model=TranscriptionResult, summary="Sesi metne çevir")
async def transcribe(
    stt: STTDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    vad_filter: bool = Form(default=False),
) -> TranscriptionResult:
    """Mikrofon kaydını Türkçe metne çevirir."""
    audio = await file.read()
    await file.close()

    if not audio:
        raise ValidationError("Ses verisi boş.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValidationError(f"Ses dosyası çok büyük ({len(audio) / 1e6:.1f} MB). Sınır: 25 MB.")

    return await stt.transcribe(
        audio,
        file.filename or "audio.webm",
        language=language or settings.whisper_language,
        vad_filter=vad_filter,
    )

@router.get("/tts/voices", response_model=VoiceListResponse, summary="TTS sesleri")
async def tts_voices(tts: TTSDep, settings: SettingsDep) -> VoiceListResponse:
    """Kurulu ve kurulabilir Piper seslerini listeler."""
    return VoiceListResponse(voices=await tts.voices(), active=settings.tts_voice)

@router.get("/tts/status", summary="TTS durumu")
async def tts_status(tts: TTSDep) -> dict[str, object]:
    """Piper servisinin durumu ve aktif ses."""
    return await tts.status()

@router.post(
    "/tts/synthesize",
    summary="Metni seslendir",
    responses={200: {"content": {"audio/wav": {}}, "description": "WAV ses verisi"}},
)
async def synthesize(payload: SynthesizeRequest, tts: TTSDep) -> Response:
    """Metni WAV sesine çevirir."""
    audio = await tts.synthesize(payload.text, voice=payload.voice, speed=payload.speed)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "Content-Length": str(len(audio))},
    )
