"""Parça biriktirici — API ``stt.stream.AudioStreamBuffer`` ile aynı sözleşme."""

from __future__ import annotations

from dataclasses import dataclass, field

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
        if not chunk:
            return False
        room = self.max_bytes - len(self._buf)
        if room <= 0:
            return False
        self._buf.extend(chunk[:room])
        return len(self._buf) >= self.partial_bytes * (self.partials + 1)

    def snapshot(self) -> bytes:
        return bytes(self._buf)

    def mark_partial(self) -> None:
        self.partials += 1

    def flush(self) -> bytes:
        data = bytes(self._buf)
        self._buf.clear()
        self.partials = 0
        return data

    def __len__(self) -> int:
        return len(self._buf)

_BACKCHANNEL = ("hmm", "hm", "hı", "ha", "evet", "tamam", "peki", "ok", "okay")
HOTWORDS = "Uryx Whisper Piper Qdrant Docker"

def parse_stream_config(payload: dict) -> tuple[str, str]:
    """WS start/end: ``(language, hotwords)``. ``prefix`` varsa hotwords düşer."""
    language = str(payload.get("language") or "").strip()
    if str(payload.get("prefix") or "").strip():
        return language, ""
    raw = str(payload.get("hotwords") or "").strip()
    return language, raw or HOTWORDS

def stream_control(kind: str, *, language: str = "", hotwords: str = HOTWORDS) -> dict[str, str]:
    """Whisper WS kontrol çerçevesi."""
    payload = {"type": kind}
    if language:
        payload["language"] = language
    if hotwords:
        payload["hotwords"] = hotwords
    return payload

def should_emit_partial(previous: str, text: str) -> bool:
    """Boş, tekrar veya tek başına onay partial'ı yayınlama."""
    cleaned = (text or "").strip()
    if not cleaned or cleaned == (previous or "").strip():
        return False
    folded = cleaned.casefold().rstrip("!.?")
    return folded not in _BACKCHANNEL and not folded.startswith("hmm")
