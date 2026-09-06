"""Hafıza geri getirme skorları — Mem0 çok-sinyalli sıralama.

Mem0 (arxiv 2504.19413): semantik + anahtar kelime füzyonundan sonra
önem, tazelik ve varlık eşleşmesi. Cross-encoder yok; CPU'da ucuz.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

DEFAULT_HALF_LIFE_DAYS = 14.0

_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,48})[\"“”']")
_PROPER = re.compile(r"\b[A-ZÇĞİÖŞÜ][\wçğıöşü.-]{2,}\b")
_TOKEN = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{4,}")
_STOP = {
    "benim",
    "senin",
    "onun",
    "bana",
    "sana",
    "nedir",
    "nasıl",
    "hangi",
    "neydi",
    "hatırla",
    "lütfen",
    "olarak",
    "için",
    "gibi",
    "kadar",
    "daha",
    "çok",
    "bunu",
    "şunu",
    "neden",
    "niçin",
    "this",
    "that",
    "what",
    "when",
    "where",
    "your",
    "have",
    "with",
    "from",
    "about",
}

def recency_score(
    when: datetime | None,
    *,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Üstel zaman azalması: bugün 1.0, yarı ömürde 0.5, çok eskide ~0."""
    if when is None:
        return 0.35
    current = now or datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    age_days = max(0.0, (current - when).total_seconds() / 86400.0)
    half_life = max(0.5, half_life_days)
    return max(0.05, min(1.0, 0.5 ** (age_days / half_life)))

def extract_entities(text: str) -> list[str]:
    """Sorgudan ayırt edici varlıklar (Mem0 entity linking'in ucuz karşılığı)."""
    if not text.strip():
        return []
    found: list[str] = [item.strip() for item in _QUOTED.findall(text) if item.strip()]
    found.extend(_PROPER.findall(text))
    for token in _TOKEN.findall(text):
        if token.casefold() in _STOP:
            continue
        found.append(token)

    seen: set[str] = set()
    unique: list[str] = []
    for item in found:
        key = item.casefold()
        if key in seen or len(key) < 3:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= 12:
            break
    return unique

def entity_overlap(entities: list[str], content: str) -> float:
    """Sorgu varlıklarının kayıtta geçme oranı (0–1)."""
    if not entities:
        return 0.0
    haystack = content.casefold()
    hits = sum(1 for entity in entities if entity.casefold() in haystack)
    return hits / len(entities)

_CURRENT = re.compile(r"\b(şimdi|su an|şu an|güncel|artık|yeni|halen)\b", re.IGNORECASE)
_PAST = re.compile(r"\b(dün|geçen|eski|önceden|o zaman|eskiden|geçmişte)\b", re.IGNORECASE)

def temporal_intent(query: str) -> str:
    """Mem0 zamansal niyet: current | past | any. LLM yok."""
    if _CURRENT.search(query):
        return "current"
    if _PAST.search(query):
        return "past"
    return "any"

def adjust_recency(recency: float, intent: str) -> float:
    """Güncel soruda tazeliği ödüllendir, geçmiş soruda eskileri öne al."""
    recency_n = max(0.0, min(1.0, recency))
    if intent == "current":
        return min(1.0, recency_n + 0.18)
    if intent == "past":
        return max(0.0, 1.0 - recency_n)
    return recency_n

def rank_memory(
    fused: float,
    importance: float,
    recency: float,
    *,
    pinned: bool = False,
    entity: float = 0.0,
) -> float:
    """Füzyon + önem + tazelik + varlık. Sabitlenmiş kayıtlar hafifçe öne alınır."""
    fused_n = max(0.0, min(1.0, fused))
    importance_n = max(0.0, min(1.0, importance))
    recency_n = max(0.0, min(1.0, recency))
    entity_n = max(0.0, min(1.0, entity))
    score = 0.48 * fused_n + 0.20 * importance_n + 0.18 * recency_n + 0.14 * entity_n
    if pinned:
        score += 0.12
    return round(min(1.0, score), 4)

def normalize_fused(raw: float, peak: float) -> float:
    """RRF ham skorunu 0–1 aralığına çeker."""
    if peak <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / peak))

EPISODE_MIN_SCORE = 0.05

def score_episode(
    query: str, summary: str, entities: list[str] | None = None
) -> float:
    """Letta arşiv yedeği: özet üzerinde kelime + varlık örtüşmesi. LLM yok."""
    if not summary.strip() or not query.strip():
        return 0.0
    ents = entities if entities is not None else extract_entities(query)
    entity = entity_overlap(ents, summary)
    tokens = {
        token.casefold()
        for token in _TOKEN.findall(query)
        if token.casefold() not in _STOP
    }
    if not tokens:
        raw = entity
    else:
        haystack = summary.casefold()
        lexical = sum(1 for token in tokens if token in haystack) / len(tokens)
        raw = 0.55 * lexical + 0.45 * entity
    score = round(raw, 4)
    return score if score >= EPISODE_MIN_SCORE else 0.0

MEMORY_MMR_LAMBDA = 0.62

def diversify_memory_hits(
    hits: list[tuple[str, str, float]],
    top_k: int,
    *,
    lambda_mult: float = MEMORY_MMR_LAMBDA,
) -> list[tuple[str, float]]:
    """LangChain MMR: benzer kayıtları çeşitlendir. Embedding yok (Jaccard)."""
    if top_k <= 0 or not hits:
        return []
    from app.services.rag.retriever import RetrievalCandidate, mmr_select

    candidates = [
        RetrievalCandidate(chunk_id=item_id, content=content, final_score=score)
        for item_id, content, score in hits
    ]
    picked = mmr_select(candidates, top_k, lambda_mult=lambda_mult)
    return [(item.chunk_id, item.final_score) for item in picked]
