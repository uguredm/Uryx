"""Sohbet bölümü sıkıştırma — Letta sliding window + ollama-rag-memory.

LLM özeti (`summarize_turns`) yüklenemezse `compact_turns`.
Özet ``conversations.summary`` ve conversations vektörüne yazılır.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.services.llm.base import ChatMessage, LLMClient
from app.services.llm.prompts import EPISODE_SUMMARY_PROMPT

logger = get_logger(__name__)

_GREETING = re.compile(
    r"^(selam|merhaba|günaydın|gunaydin|tamam|ok|peki|evet|hayır|hayir|"
    r"teşekkürler|tesekkurler|sağol|sagol)[\s!.?]*$",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")

def compact_turns(
    turns: list[tuple[str, str]],
    *,
    keep_recent: int = 4,
    max_chars: int = 900,
) -> str:
    """Eski turları kısaltır, son turları tutar (Letta ``sliding_window``).

    Args:
        turns: ``(role, content)`` kronolojik liste.
        keep_recent: Aynen (kısaltılarak) bırakılacak son tur sayısı.
        max_chars: Özet tavanı.

    Returns:
        Boş olmayan özet veya ``""``.
    """
    cleaned = [_clip_turn(role, content) for role, content in turns if content.strip()]
    cleaned = [item for item in cleaned if item is not None]
    if len(cleaned) < 2:
        return ""

    older, recent = cleaned[:-keep_recent], cleaned[-keep_recent:]
    older_bits = [_fact_line(role, text) for role, text in older]
    older_bits = [bit for bit in older_bits if bit]

    lines: list[str] = []
    if older_bits:
        lines.append("Önceki konular: " + " · ".join(older_bits[:8]))
    for role, text in recent:
        prefix = "Kullanıcı" if role == "user" else "Asistan"
        lines.append(f"{prefix}: {text}")

    summary = _SPACE.sub(" ", "\n".join(lines)).strip()
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 1].rsplit(" ", 1)[0] + "…"

def _usable_llm_summary(text: str) -> str | None:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) < 24:
        return None
    if cleaned.startswith("{") or cleaned.startswith("["):
        return None
    if "should_save" in cleaned:
        return None
    return cleaned[:2000]

def _transcript(turns: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    for role, content in turns:
        piece = content.strip()
        if not piece:
            continue
        prefix = "Kullanıcı" if role == "user" else "Asistan"
        lines.append(f"{prefix}: {piece[:400]}")
    return "\n".join(lines[-24:])[:4000]

async def summarize_turns(
    turns: list[tuple[str, str]],
    llm: LLMClient,
    *,
    max_tokens: int = 256,
) -> str:
    """LLM ile bölüm özeti; hata/JSON/kısa cevap → ``compact_turns``."""
    fallback = compact_turns(turns)
    if not fallback:
        return ""
    blob = _transcript(turns)
    if not blob.strip():
        return fallback
    messages = [
        ChatMessage(role="system", content=EPISODE_SUMMARY_PROMPT),
        ChatMessage(role="user", content=blob),
    ]
    try:
        result = await llm.complete(
            messages,
            temperature=0.2,
            max_tokens=max_tokens,
            enable_thinking=False,
        )
    except Exception as exc:
        logger.warning("episode_summary_llm_failed", error=str(exc))
        return fallback
    return _usable_llm_summary(result.content) or fallback

def _clip_turn(role: str, content: str) -> tuple[str, str] | None:
    text = _SPACE.sub(" ", content).strip()
    if len(text) < 4:
        return None
    if role == "user" and _GREETING.match(text):
        return None
    if len(text) > 220:
        text = text[:219].rsplit(" ", 1)[0] + "…"
    return (role, text)

def _fact_line(role: str, text: str) -> str | None:
    if role != "user":
        return None
    if len(text) < 12:
        return None
    return text[:120]
