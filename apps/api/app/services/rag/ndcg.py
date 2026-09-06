"""nDCG@k (graded). Canlı BGE eval ``scripts/eval_rag_ndcg.py``; pytest formül + set."""

from __future__ import annotations

import math

def dcg_at_k(gains: list[float], k: int) -> float:
    """``sum rel_i / log2(i+1)`` ilk k konum."""
    total = 0.0
    for index, gain in enumerate(gains[:k], start=1):
        total += float(gain) / math.log2(index + 1)
    return total

def ndcg_at_k(ranked_ids: list[str], relevance: dict[str, float], k: int) -> float:
    """Sıralı kimlik listesinin nDCG@k skoru."""
    if k <= 0:
        return 0.0
    gains = [float(relevance.get(doc_id, 0.0)) for doc_id in ranked_ids[:k]]
    actual = dcg_at_k(gains, k)
    ideal_gains = sorted((float(v) for v in relevance.values()), reverse=True)
    ideal = dcg_at_k(ideal_gains, k)
    if ideal <= 0:
        return 0.0
    return actual / ideal

def mean_ndcg(rows: list[tuple[list[str], dict[str, float]]], k: int) -> float:
    """Birden fazla sorgunun ortalama nDCG@k."""
    if not rows:
        return 0.0
    return sum(ndcg_at_k(ranked, rel, k) for ranked, rel in rows) / len(rows)
