"""Whisper parça akışı — LiveKit/faster-whisper chunked streaming.

Masaüstü tam klip bekler; bu oturum bayt biriktirir, eşik dolunca partial,
flush'ta final üretir. LLM/HyDE yok.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.stt.quality import DEFAULT_HOTWORDS

PARTIAL_MIN_BYTES = 24_000
MAX_BUFFER_BYTES = 2_000_000

@dataclass
class AudioStreamBuffer:
    """Ham ses parçalarını biriktirir; partial/final kararını verir."""

    partial_bytes: int = PARTIAL_MIN_BYTES
    max_bytes: int = MAX_BUFFER_BYTES
    _buf: bytearray = field(default_factory=bytearray)
    partials: int = 0

    def feed(self, chunk: bytes) -> bool:
        """Parça ekler. Partial transkripsiyon zamanıysa True."""
        if not chunk:
            return False
        room = self.max_bytes - len(self._buf)
        if room <= 0:
            return False
        self._buf.extend(chunk[:room])
        return len(self._buf) >= self.partial_bytes * (self.partials + 1)

    def snapshot(self) -> bytes:
        """Birikmiş sesin kopyası (partial decode için)."""
        return bytes(self._buf)

    def mark_partial(self) -> None:
        """Bir partial üretildi."""
        self.partials += 1

    def flush(self) -> bytes:
        """Tamponu boşaltır ve final decode için baytları verir."""
        data = bytes(self._buf)
        self._buf.clear()
        self.partials = 0
        return data

    def __len__(self) -> int:
        return len(self._buf)

def parse_stream_event(payload: dict[str, object]) -> tuple[str, str]:
    """Whisper WS olayını ``(kind, text)`` olarak okur."""
    kind = str(payload.get("type") or payload.get("kind") or "")
    text = str(payload.get("text") or "").strip()
    if kind not in {"partial", "final", "error"}:
        kind = "partial" if text else "error"
    return kind, text

def parse_stream_config(payload: dict[str, object]) -> tuple[str, str]:
    """WS start/end: ``(language, hotwords)``. ``prefix`` varsa hotwords düşer."""
    language = str(payload.get("language") or "").strip()
    if str(payload.get("prefix") or "").strip():
        return language, ""
    raw = str(payload.get("hotwords") or "").strip()
    return language, raw or DEFAULT_HOTWORDS

def stream_control(
    kind: str, *, language: str = "", hotwords: str = DEFAULT_HOTWORDS
) -> dict[str, str]:
    """Whisper WS kontrol çerçevesi (start/flush/end)."""
    payload = {"type": kind}
    if language:
        payload["language"] = language
    if hotwords:
        payload["hotwords"] = hotwords
    return payload

def should_emit_partial(previous: str, text: str) -> bool:
    """faster-whisper #1127 + LiveKit: boş / aynı / mırıldanma partial gitmez."""
    from app.services.stt.quality import is_backchannel

    cleaned = (text or "").strip()
    if not cleaned or cleaned == (previous or "").strip():
        return False
    return not is_backchannel(cleaned)
