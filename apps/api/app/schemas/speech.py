"""STT / TTS şemaları."""

from __future__ import annotations

from pydantic import BaseModel, Field

class TranscriptionSegment(BaseModel):
    """Transkripsiyon parçası."""

    start: float
    end: float
    text: str

class TranscriptionResult(BaseModel):
    """Konuşma tanıma sonucu."""

    text: str
    language: str = "tr"
    duration: float = 0.0
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    model: str = ""
    device: str = ""

class SynthesizeRequest(BaseModel):
    """Seslendirme isteği."""

    text: str = Field(min_length=1, max_length=5000)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    volume: float | None = Field(default=None, ge=0.0, le=2.0)

class VoiceInfo(BaseModel):
    """Kullanılabilir ses."""

    id: str
    name: str
    language: str
    quality: str = "medium"
    installed: bool = False

class VoiceListResponse(BaseModel):
    """Ses listesi."""

    voices: list[VoiceInfo] = Field(default_factory=list)
    active: str | None = None

class WhisperModelInfo(BaseModel):
    """Whisper model bilgisi."""

    id: str
    name: str
    size_mb: int
    loaded: bool = False

class STTStatus(BaseModel):
    """STT servis durumu."""

    available: bool
    model: str = ""
    device: str = ""
    language: str = "tr"
    detail: str | None = None

class STTReloadRequest(BaseModel):
    """Whisper modelini canlı yeniden yükle."""

    model: str = Field(min_length=1, max_length=60)
