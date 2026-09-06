"""Hybrid retrieval ve yeniden sıralama (reranking).

Akış: dense (Qdrant) + sparse (PostgreSQL full-text) → Reciprocal Rank Fusion →
cross-encoder rerank (yüklenemezse sinyal) → ilk ``top_k``.

``Reranker`` protokolü: ``SignalReranker`` ve ``CrossEncoderReranker``.
Embedding boyutu bu modülde değişmez (MiniLM 384; D9).
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Protocol, TypeVar, runtime_checkable

from app.core.config import Settings
from app.core.logging import get_logger

_T = TypeVar("_T")
logger = get_logger(__name__)

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

RRF_K = 60

VECTOR_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3

TITLE_FIELD_WEIGHT = 10.0
CONTENT_FIELD_WEIGHT = 2.0

OBJECTS_PER_GROUP = 2

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_QUERY_FILLER = re.compile(
    r"\b(lütfen|acaba|bana|söyler\s+misin|anlatır\s+mısın|"
    r"hatırlıyor\s+musun|nedir|neydi|nasıl|hangi)\b",
    re.IGNORECASE,
)

@dataclass(slots=True)
class RetrievalCandidate:
    """Füzyon ve rerank aşamalarındaki aday."""

    chunk_id: str
    document_id: str = ""
    filename: str = ""
    content: str = ""
    page: int | None = None
    chunk_index: int = 0
    dense_score: float = 0.0
    sparse_score: float = 0.0
    fused_score: float = 0.0
    final_score: float = 0.0
    signals: dict[str, float] = field(default_factory=dict)

def reciprocal_rank_fusion(
    dense: list[tuple[str, float]],
    sparse: list[tuple[str, float]],
    *,
    dense_weight: float = 1.0,
    sparse_weight: float = 0.8,
) -> dict[str, float]:
    """İki sıralı listeyi RRF ile birleştirir.

    Args:
        dense: ``(chunk_id, skor)`` — vektör araması, skora göre sıralı.
        sparse: ``(chunk_id, skor)`` — full-text araması, skora göre sıralı.
        dense_weight: Dense listenin ağırlığı.
        sparse_weight: Sparse listenin ağırlığı.

    Returns:
        ``chunk_id`` → füzyon skoru.
    """
    fused: dict[str, float] = {}
    for rank, (chunk_id, _score) in enumerate(dense, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + dense_weight / (RRF_K + rank)
    for rank, (chunk_id, _score) in enumerate(sparse, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + sparse_weight / (RRF_K + rank)
    return fused

def rescale_dbsf(scores: list[float]) -> list[float]:
    """Haystack DBSF: ``(score - (μ-3σ)) / 6σ``. Hepsi eşitse 0."""
    if not scores:
        return []
    if max(scores) - min(scores) == 0:
        return [0.0] * len(scores)
    mean = sum(scores) / len(scores)
    std_dev = (sum((value - mean) ** 2 for value in scores) / len(scores)) ** 0.5
    min_score = mean - 3 * std_dev
    delta = 6 * std_dev
    if delta == 0:
        return [0.0] * len(scores)
    return [(value - min_score) / delta for value in scores]

def distribution_based_fusion(
    dense: list[tuple[str, float]],
    sparse: list[tuple[str, float]],
) -> dict[str, float]:
    """Haystack ``distribution_based_rank_fusion``: listede ölçekle, çakışmada max."""
    fused: dict[str, float] = {}
    for ranking in (dense, sparse):
        if not ranking:
            continue
        scaled = rescale_dbsf([score for _chunk_id, score in ranking])
        for (chunk_id, _raw), score in zip(ranking, scaled, strict=True):
            previous = fused.get(chunk_id)
            fused[chunk_id] = score if previous is None else max(previous, score)
    return fused

@runtime_checkable
class Reranker(Protocol):
    """Yeniden sıralayıcı sözleşmesi."""

    async def rerank(
        self, query: str, candidates: list[RetrievalCandidate], top_k: int
    ) -> list[RetrievalCandidate]:
        """Adayları sorguya göre yeniden sıralar."""
        ...

class SignalReranker:
    """Hafif, model gerektirmeyen reranker.

    Dört sinyali birleştirir:

    1. ``fusion``   — RRF skoru (normalize edilmiş).
    2. ``coverage`` — sorgu kelimelerinin parçada kaçının geçtiği.
    3. ``proximity``— eşleşen kelimelerin birbirine yakınlığı.
    4. ``density``  — eşleşme yoğunluğu (uzun parçaları cezalandırır).
    """

    def __init__(
        self,
        *,
        fusion_weight: float = 0.45,
        coverage_weight: float = 0.30,
        proximity_weight: float = 0.15,
        density_weight: float = 0.10,
    ) -> None:
        self._weights = {
            "fusion": fusion_weight,
            "coverage": coverage_weight,
            "proximity": proximity_weight,
            "density": density_weight,
        }

    async def rerank(
        self, query: str, candidates: list[RetrievalCandidate], top_k: int
    ) -> list[RetrievalCandidate]:
        """Sinyalleri hesaplayıp adayları sıralar."""
        if not candidates:
            return []

        terms = _tokenize(query)
        max_fusion = max((c.fused_score for c in candidates), default=0.0) or 1.0

        for candidate in candidates:
            tokens = _tokenize(candidate.content)
            token_set = set(tokens)

            fusion = candidate.fused_score / max_fusion
            coverage = (
                sum(1 for t in terms if _term_covered(t, token_set)) / len(terms) if terms else 0.0
            )
            proximity = _proximity(tokens, terms)
            hits = sum(tokens.count(t) for t in terms)
            density = min(hits / max(math.log(len(tokens) + 2, 2), 1.0), 1.0)

            candidate.signals = {
                "fusion": round(fusion, 4),
                "coverage": round(coverage, 4),
                "proximity": round(proximity, 4),
                "density": round(density, 4),
            }
            candidate.final_score = round(
                sum(self._weights[k] * v for k, v in candidate.signals.items()), 6
            )

        candidates.sort(key=lambda c: c.final_score, reverse=True)
        return candidates[:top_k]

class CrossEncoderReranker:
    """``BAAI/bge-reranker-v2-m3`` CPU. Yükleme/predict hatası → SignalReranker.

    MiniLM embedding boyutuna dokunmaz (D9 / D14).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        encoder: object | None = None,
        fallback: Reranker | None = None,
        loader: Callable[[], object] | None = None,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        self._encoder = encoder
        self._fallback = fallback or SignalReranker()
        self._loader = loader
        self._model_name = model_name or (
            settings.rag_rerank_model if settings is not None else DEFAULT_RERANK_MODEL
        )
        requested = device or (
            settings.rag_rerank_device if settings is not None else "cpu"
        )
        if str(requested).lower() != "cpu":
            logger.warning("rerank_forced_cpu", requested=requested)
        self._device = "cpu"
        self._using_fallback = False
        self._lock = asyncio.Lock()

    @property
    def using_fallback(self) -> bool:
        """Cross-encoder yüklenemedi; SignalReranker yedeği aktif mi?"""
        return self._using_fallback

    async def load(self) -> None:
        """Modeli önceden yükler; başarısız olursa sinyal yedeğine düşer."""
        await self._ensure_encoder()

    async def _ensure_encoder(self) -> object | None:
        if self._encoder is not None:
            return self._encoder
        if self._using_fallback:
            return None
        async with self._lock:
            if self._encoder is not None or self._using_fallback:
                return self._encoder
            try:
                self._encoder = await asyncio.to_thread(self._load_sync)
            except Exception as exc:
                self._using_fallback = True
                logger.warning(
                    "rerank_model_failed_using_signal",
                    model=self._model_name,
                    error=str(exc),
                )
                return None
        return self._encoder

    def _load_sync(self) -> object:
        if self._loader is not None:
            return self._loader()
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self._model_name, device=self._device)

    async def rerank(
        self, query: str, candidates: list[RetrievalCandidate], top_k: int
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        encoder = await self._ensure_encoder()
        if encoder is None:
            return await self._fallback.rerank(query, candidates, top_k)
        pairs = [(query, candidate.content) for candidate in candidates]
        try:
            raw = await asyncio.to_thread(encoder.predict, pairs)
            scores = [float(score) for score in raw]
        except Exception as exc:
            logger.warning("rerank_predict_failed_using_signal", error=str(exc))
            return await self._fallback.rerank(query, candidates, top_k)
        if len(scores) != len(candidates):
            return await self._fallback.rerank(query, candidates, top_k)
        for candidate, score in zip(candidates, scores, strict=True):
            candidate.signals = {**candidate.signals, "cross": round(score, 4)}
            candidate.final_score = score
        candidates.sort(key=lambda item: item.final_score, reverse=True)
        return candidates[:top_k]

def create_reranker(settings: Settings) -> Reranker:
    """Ayarlara göre cross-encoder veya sinyal reranker."""
    if not settings.rag_rerank_enabled:
        return SignalReranker()
    return CrossEncoderReranker(settings)

def keyword_overlap_score(query: str, text: str) -> float:
    """Odysseus kelime örtüşmesi: eşleşen sorgu kelimesi / sorgu kelimesi."""
    words = [token for token in query.casefold().split() if len(token) > 1]
    if not words or not text.strip():
        return 0.0
    haystack = text.casefold()
    return sum(1 for word in words if word in haystack) / len(words)

def filename_search_text(filename: str) -> str:
    """Dosya adını RAGFlow ``title_tks`` gibi aranabilir metne çevirir."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return re.sub(r"[_\-.]+", " ", name).strip()

def lexical_with_title(query: str, content: str, filename: str = "") -> float:
    """RAGFlow çok-alan: içerik + başlık. Başlık yoksa içerik dilinmez."""
    content_s = keyword_overlap_score(query, content)
    title_s = keyword_overlap_score(query, filename_search_text(filename)) if filename else 0.0
    if title_s <= 0:
        return content_s
    title_mix = TITLE_FIELD_WEIGHT / (TITLE_FIELD_WEIGHT + CONTENT_FIELD_WEIGHT)
    return round(min(1.0, content_s + title_mix * title_s), 4)

def hybrid_vector_keyword(
    vector_sim: float, query: str, text: str, filename: str = ""
) -> float:
    """Odysseus: ``0.7 * vector + 0.3 * keyword``. Vektör 0–1 varsayılır."""
    vector_n = max(0.0, min(1.0, vector_sim))
    keyword = lexical_with_title(query, text, filename)
    return round(VECTOR_WEIGHT * vector_n + KEYWORD_WEIGHT * keyword, 4)

def expand_retrieval_query(query: str) -> str:
    """Open WebUI sorgu sadeleştirme: dolgu kelimeleri at, çekirdeği bırak."""
    cleaned = _QUERY_FILLER.sub(" ", query)
    cleaned = " ".join(cleaned.split())
    return cleaned or query.strip()

def hypothetical_passage(query: str) -> str:
    """HyDE-lite: soruyu cevap biçimli pasaja çevirir, LLM çağırmaz.

    Dense gömme bu metni kullanır; sparse hâlâ sade anahtar kelimede kalır.
    """
    core = expand_retrieval_query(query)
    if not core:
        return query.strip()
    lowered = query.casefold()
    if any(token in lowered for token in ("nedir", "ne demek")):
        return f"{core} tanımı ve açıklaması. {core} hakkında bilgi."
    if "nasıl" in lowered:
        return f"{core} adımları, yöntemi ve uygulaması."
    if any(token in lowered for token in ("nerede", "hangi")):
        return f"{core} konumu, seçenekleri ve kullanımı."
    if any(token in lowered for token in ("kim", "neydi")):
        return f"{core} kaydı ve hatırlanan bilgi."
    return core

def stitch_neighbor_text(
    center: str,
    previous: str | None,
    nxt: str | None,
    *,
    max_chars: int = 1600,
) -> str:
    """Eşleşen parçayı komşularıyla birleştirir (LlamaIndex sentence-window)."""
    parts = [piece for piece in (previous, center, nxt) if piece and piece.strip()]
    joined = "\n".join(parts).strip()
    if len(joined) <= max_chars:
        return joined
    if previous:
        overflow = max(0, len(joined) - max_chars)
        trimmed_prev = previous[overflow:] if overflow < len(previous) else ""
        joined = "\n".join(p for p in (trimmed_prev, center, nxt) if p and p.strip())
    return joined[:max_chars]

def cluster_adjacent(
    candidates: list[RetrievalCandidate], *, gap: int = 1
) -> list[list[RetrievalCandidate]]:
    """Aynı belgede bitişik parçaları gruplar (LlamaIndex auto-merge)."""
    if not candidates:
        return []

    by_doc: dict[str, list[RetrievalCandidate]] = {}
    order: list[str] = []
    for candidate in candidates:
        key = candidate.document_id or candidate.chunk_id
        if key not in by_doc:
            order.append(key)
            by_doc[key] = []
        by_doc[key].append(candidate)

    clusters: list[list[RetrievalCandidate]] = []
    for key in order:
        group = sorted(by_doc[key], key=lambda item: item.chunk_index)
        current = [group[0]]
        for item in group[1:]:
            if item.chunk_index - current[-1].chunk_index <= gap:
                current.append(item)
            else:
                clusters.append(current)
                current = [item]
        clusters.append(current)

    clusters.sort(key=lambda cluster: max(item.final_score for item in cluster), reverse=True)
    return clusters

def lost_in_the_middle(items: list[_T]) -> list[_T]:
    """Haystack: en iyi uçlarda, zayıf ortada (Lost in the Middle, arxiv 2307.03172).

    Girdi alaka sırasındadır. 0 ve 1'den kısa liste olduğu gibi kalır.
    """
    if len(items) <= 2:
        return list(items)
    order = [0]
    for index in range(1, len(items)):
        insertion = len(order) // 2 + len(order) % 2
        order.insert(insertion, index)
    return [items[index] for index in order]

def autocut_index(scores: list[float], jumps: int = 1) -> int:
    """Weaviate Autocut: sıralı skorlarda ``jumps`` ekstremadan sonra kes.

    Skorlar yüksekten düşüğe olmalı. İlk == son ise sıfıra bölünmez, hepsi kalır.
    ``jumps <= 0`` veya tek eleman → liste boyu.
    """
    if jumps <= 0 or len(scores) <= 1:
        return len(scores)
    span = scores[-1] - scores[0]
    if span == 0:
        return len(scores)

    step = 1.0 / (len(scores) - 1)
    diff = [((score - scores[0]) / span) - (index * step) for index, score in enumerate(scores)]

    extrema = 0
    last = len(diff) - 1
    for index in range(1, len(diff)):
        if index == last and last > 0:
            is_peak = diff[index] > diff[index - 1] and diff[index] > diff[index - 2]
        else:
            is_peak = diff[index] > diff[index - 1] and diff[index] > diff[index + 1]
        if not is_peak:
            continue
        extrema += 1
        if extrema >= jumps:
            return index
    return len(scores)

def cap_per_document(
    candidates: list[RetrievalCandidate], *, max_per: int = OBJECTS_PER_GROUP
) -> list[RetrievalCandidate]:
    """Weaviate groupBy: her ``document_id`` için en fazla ``max_per`` parça."""
    if max_per <= 0 or not candidates:
        return list(candidates)
    seen: dict[str, int] = {}
    kept: list[RetrievalCandidate] = []
    for item in candidates:
        key = item.document_id or item.chunk_id
        count = seen.get(key, 0)
        if count >= max_per:
            continue
        seen[key] = count + 1
        kept.append(item)
    return kept

def autocut(
    candidates: list[RetrievalCandidate], *, jumps: int = 1
) -> list[RetrievalCandidate]:
    """Verba/Weaviate: rerank sonrası skor uçurumunda kuyruğu at."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: item.final_score, reverse=True)
    cut = autocut_index([item.final_score for item in ordered], jumps)
    return ordered[:cut]

def mmr_select(
    candidates: list[RetrievalCandidate],
    top_k: int,
    *,
    lambda_mult: float = 0.72,
) -> list[RetrievalCandidate]:
    """Maximal Marginal Relevance — benzer pasajları çeşitlendirir.

    AnythingLLM/Open WebUI aynı paragraftan 4 neredeyse özdeş parça döndürebilir.
    MMR, alaka ile yeniliği karıştırır; cross-encoder gerektirmez.
    """
    if top_k <= 0 or not candidates:
        return []
    if lambda_mult <= 0 or len(candidates) <= top_k:
        return candidates[:top_k]

    selected = [candidates[0]]
    remaining = list(candidates[1:])
    selected_tokens = [_token_set(candidates[0].content)]
    lam = min(1.0, max(0.0, lambda_mult))

    while remaining and len(selected) < top_k:
        best_index = 0
        best_score = -1.0
        for index, candidate in enumerate(remaining):
            tokens = _token_set(candidate.content)
            similarity = max((_jaccard(tokens, prior) for prior in selected_tokens), default=0.0)
            score = lam * candidate.final_score - (1.0 - lam) * similarity
            if score > best_score:
                best_score = score
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_tokens.append(_token_set(chosen.content))
    return selected

def _token_set(text: str) -> set[str]:
    """Jaccard için kelime kümesi."""
    return set(_tokenize(text))

def _jaccard(left: set[str], right: set[str]) -> float:
    """İki kelime kümesinin Jaccard benzerliği."""
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0

def merge_cluster_text(cluster: list[RetrievalCandidate], *, max_chars: int = 1600) -> str:
    """Bitişik adayları tek pasajda birleştirir (LlamaIndex auto-merge)."""
    if not cluster:
        return ""
    ordered = sorted(cluster, key=lambda item: item.chunk_index)
    joined = "\n".join(item.content.strip() for item in ordered if item.content.strip())
    return joined[:max_chars]

def _tokenize(text: str) -> list[str]:
    """Küçük harfe indirgenmiş kelime listesi."""
    return _WORD_RE.findall(text.lower())

_TR_SUFFIXES = (
    "ları",
    "leri",
    "ların",
    "lerin",
    "ndan",
    "nden",
    "dan",
    "den",
    "tan",
    "ten",
    "nın",
    "nin",
    "nun",
    "nün",
    "lar",
    "ler",
)

def _term_covered(term: str, token_set: set[str]) -> bool:
    """Türkçe ekleri kabaca soyarak kelime kapsamasını ölçer."""
    if term in token_set:
        return True
    if len(term) < 4:
        return False
    for suffix in _TR_SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 3:
            stem = term[: -len(suffix)]
            if stem in token_set:
                return True
    return any(
        token.startswith(term) or term.startswith(token)
        for token in token_set
        if len(token) >= 4
    )

def _proximity(tokens: list[str], terms: list[str]) -> float:
    """Eşleşen sorgu kelimelerinin yakınlığını 0–1 aralığında ölçer."""
    if len(terms) < 2:
        return 1.0 if terms and terms[0] in tokens else 0.0

    positions: list[int] = [i for i, tok in enumerate(tokens) if tok in set(terms)]
    if len(positions) < 2:
        return 0.0

    best = min(b - a for a, b in pairwise(positions))

    return max(0.0, 1.0 - math.log(best + 1, 2) / math.log(52, 2))
