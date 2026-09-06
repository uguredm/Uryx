"""Microsoft Edge Neural TTS (Türkçe Ahmet/Emel).

Piper yedek kalır. Bu motor internet ister; yerel-önce mimariyi bozmaz —
çağıran taraf başarısız olursa Piper'a düşer.

Edge servisi ``Sec-MS-GEC`` imzası ister; imza saat dilimine bağlı olduğu için
sunucu saatiyle sapma düzeltmesi yapılır.
"""

from __future__ import annotations

import hashlib
import io
import logging
import struct
import time
import uuid
import wave
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
import miniaudio
import websockets

logger = logging.getLogger("tts.edge")

TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
BASE_URL = "api.msedgeservices.com/tts/cognitiveservices"
EDGE_ENDPOINT = f"wss://{BASE_URL}/websocket/v1?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
VOICE_LIST_URL = f"https://{BASE_URL}/voices/list?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
SEC_MS_GEC_VERSION = "1-140.0.3485.14"

WIN_EPOCH = 11_644_473_600
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
SAMPLE_RATE = 24000

_clock_skew = 0.0

EDGE_VOICES: dict[str, dict[str, str]] = {
    "tr-TR-AhmetNeural": {
        "name": "Ahmet (Türkçe, nöral)",
        "language": "tr",
        "quality": "neural",
    },
    "tr-TR-EmelNeural": {
        "name": "Emel (Türkçe, nöral)",
        "language": "tr",
        "quality": "neural",
    },
    "en-US-GuyNeural": {
        "name": "Guy (English, neural)",
        "language": "en",
        "quality": "neural",
    },
    "en-US-JennyNeural": {
        "name": "Jenny (English, neural)",
        "language": "en",
        "quality": "neural",
    },
}

def is_edge_voice(voice_id: str | None) -> bool:
    """Ses Edge Neural kataloğunda mı?"""
    return bool(voice_id) and voice_id in EDGE_VOICES

def piper_fallback_voice(voice_id: str | None) -> str:
    """Edge düşünce Piper yedeği: EN → lessac, TR → dfki."""
    meta = EDGE_VOICES.get(voice_id or "")
    if meta and meta.get("language") == "en":
        return "en_US-lessac-medium"
    return "tr_TR-dfki-medium"

def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Ham 16-bit mono PCM'i WAV konteynerine koyar."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()

def mp3_to_wav(mp3: bytes) -> bytes:
    """Edge'in MP3 çıkışını 16-bit mono WAV'a çevirir."""
    decoded = miniaudio.decode(
        mp3,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=SAMPLE_RATE,
    )
    return pcm_to_wav(decoded.samples.tobytes(), decoded.sample_rate)

def _sec_ms_gec() -> str:
    """Edge'in beklediği zaman tabanlı SHA256 imzasını üretir."""
    ticks = int(time.time() + _clock_skew) + WIN_EPOCH
    ticks -= ticks % 300
    ticks *= 10_000_000
    return hashlib.sha256(f"{ticks}{TRUSTED_CLIENT_TOKEN}".encode("ascii")).hexdigest().upper()

async def _sync_clock_skew() -> bool:
    """Sunucunun ``Date`` başlığından saat sapmasını hesaplar."""
    global _clock_skew
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.head(VOICE_LIST_URL)
        server_date = response.headers.get("date")
        if not server_date:
            return False
        skew = parsedate_to_datetime(server_date).timestamp() - time.time()
    except Exception as exc:  # noqa: BLE001 - imza yenilenemezse Piper yedeği kalır
        logger.warning("Edge saat sapması alınamadı: %s", exc)
        return False
    if abs(skew - _clock_skew) < 1:
        return False
    _clock_skew = skew
    logger.info("Edge saat sapması güncellendi: %.1f sn", skew)
    return True

def _rate_percent(speed: float) -> str:
    delta = int(round((max(0.5, min(speed, 2.0)) - 1.0) * 100))
    return f"{delta:+d}%"

def _ssml(text: str, voice: str, speed: float) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='tr-TR'>"
        f"<voice name='{voice}'><prosody rate='{_rate_percent(speed)}'>{escaped}</prosody></voice>"
        "</speak>"
    )

def _headers() -> dict[str, str]:
    return {
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Origin": "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
        ),
    }

async def _stream_audio(text: str, *, voice: str, speed: float) -> bytes:
    """Tek bir websocket turunda MP3 baytlarını toplar."""
    request_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%a %b %d %Y %H:%M:%S GMT+0000")
    config = (
        "X-Timestamp:" + timestamp + "\r\n"
        "Content-Type:application/json; charset=utf-8\r\n"
        "Path:speech.config\r\n\r\n"
        '{"context":{"synthesis":{"audio":{"metadataoptions":'
        '{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},'
        '"outputFormat":"' + OUTPUT_FORMAT + '"}}}}\r\n'
    )
    ssml = (
        f"X-RequestId:{request_id}\r\n"
        "Content-Type:application/ssml+xml\r\n"
        f"X-Timestamp:{timestamp}\r\n"
        "Path:ssml\r\n\r\n" + _ssml(text, voice, speed)
    )

    audio = bytearray()
    url = (
        f"{EDGE_ENDPOINT}&ConnectionId={uuid.uuid4().hex}"
        f"&Sec-MS-GEC={_sec_ms_gec()}&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )
    async with websockets.connect(
        url,
        additional_headers=_headers(),
        max_size=None,
        open_timeout=10,
        close_timeout=4,
    ) as socket:
        await socket.send(config)
        await socket.send(ssml)
        while True:
            message = await socket.recv()
            if isinstance(message, bytes):
                if len(message) < 2:
                    continue
                header_len = struct.unpack_from(">H", message)[0]
                audio.extend(message[2 + header_len :])
                continue
            if "Path:turn.end" in message:
                break
    return bytes(audio)

async def synthesize_edge(text: str, *, voice: str, speed: float = 1.0) -> bytes:
    """Metni Edge Neural ile WAV baytlarına çevirir."""
    if voice not in EDGE_VOICES:
        raise ValueError(f"Bilinmeyen Edge sesi: {voice}")

    try:
        audio = await _stream_audio(text, voice=voice, speed=speed)
    except websockets.exceptions.InvalidStatus as exc:
        status = exc.response.status_code
        if status not in {401, 403} or not await _sync_clock_skew():
            raise
        logger.info("Edge imzası yenilendi, istek tekrarlanıyor (HTTP %s).", status)
        audio = await _stream_audio(text, voice=voice, speed=speed)

    if not audio:
        raise RuntimeError("Edge TTS ses üretemedi.")
    return mp3_to_wav(audio)
