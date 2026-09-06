"""Whisper parça kalitesi — faster-whisper metrikleri.

Sessizlikte model ``no_speech_prob`` yüksek / ``avg_logprob`` düşük parçalar
üretir; OpenAI Whisper ve faster-whisper demoları bunları atar. Tekrarlayan
halüsinasyonlar ``compression_ratio`` ile yakalanır.
"""

from __future__ import annotations

import re

DEFAULT_NO_SPEECH = 0.65
DEFAULT_MIN_LOGPROB = -1.15
DEFAULT_MAX_COMPRESSION = 2.4

DEFAULT_HOTWORDS = "Uryx Whisper Piper Qdrant Docker"

_BACKCHANNEL = re.compile(
    r"^(hm+|hı+|hmm+|ha+|evet|tamam|peki|ok|okay|ün-h[uü]m)[\s!.?]*$",
    re.IGNORECASE,
)

def is_low_quality_segment(
    *,
    no_speech_prob: float | None = None,
    avg_logprob: float | None = None,
    compression_ratio: float | None = None,
    no_speech_threshold: float = DEFAULT_NO_SPEECH,
    min_avg_logprob: float = DEFAULT_MIN_LOGPROB,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION,
) -> bool:
    """Parça sessizlik veya halüsinasyon adayı mı?

    faster-whisper ``transcribe.py``: yüksek ``no_speech_prob`` tek başına yetmez;
    logprob eşiğin üstündeyse (konuşma güveni) parça tutulur.
    """
    if no_speech_prob is not None and no_speech_prob >= no_speech_threshold:
        if avg_logprob is None or avg_logprob <= min_avg_logprob:
            return True
    if avg_logprob is not None and avg_logprob < min_avg_logprob:
        return True
    return (
        compression_ratio is not None and compression_ratio > max_compression_ratio
    )

def is_backchannel(text: str) -> bool:
    """LiveKit adaptive interruption: tek başına onay/mırıldanma tur değil."""
    return bool(_BACKCHANNEL.match((text or "").strip()))

def whisper_decode_hints(*, prefix: str | None = None) -> dict[str, str]:
    """faster-whisper: ``hotwords`` her pencere; ``prefix`` set ise hotwords düşer."""
    cleaned = (prefix or "").strip()
    if cleaned:
        return {"prefix": cleaned}
    return {"hotwords": DEFAULT_HOTWORDS}
