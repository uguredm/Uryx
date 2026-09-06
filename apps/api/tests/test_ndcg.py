"""nDCG@k — Signal vs cross-encoder rerank ölçümü (canlı BGE eval pytest'te yok)."""

from __future__ import annotations

from app.services.rag.ndcg import dcg_at_k, mean_ndcg, ndcg_at_k
from app.services.rag.ndcg_cases import NDCG_CASES
from app.services.rag.retriever import RetrievalCandidate, SignalReranker

class TestNdcgFormula:
    def test_mukemmel_siralama_bir(self) -> None:
        ranked = ["a", "b", "c"]
        rel = {"a": 3, "b": 2, "c": 1}
        assert ndcg_at_k(ranked, rel, 3) == 1.0

    def test_ters_siralama_dusuk(self) -> None:
        rel = {"a": 3, "b": 2, "c": 1}
        assert ndcg_at_k(["c", "b", "a"], rel, 3) < ndcg_at_k(["a", "b", "c"], rel, 3)

    def test_bos_sifir(self) -> None:
        assert ndcg_at_k([], {"a": 1}, 5) == 0.0
        assert dcg_at_k([], 5) == 0.0

    def test_k_siniri(self) -> None:
        assert ndcg_at_k(["a", "b", "c"], {"a": 1, "b": 1, "c": 0}, 2) == 1.0

    def test_ortalama(self) -> None:
        rows = [
            (["a", "b"], {"a": 1, "b": 0}),
            (["x", "y"], {"y": 1, "x": 0}),
        ]
        mixed = mean_ndcg(rows, 2)
        assert 0.0 < mixed < 1.0

class TestNdcgCases:
    def test_en_az_yirmi_tr_cift(self) -> None:
        assert len(NDCG_CASES) >= 20
        queries = {case["query"] for case in NDCG_CASES}
        assert len(queries) >= 20
        for case in NDCG_CASES:
            assert " " in case["query"]
            assert case["relevance"]
            assert len(case["docs"]) >= 4
            ids = {doc["id"] for doc in case["docs"]}
            assert set(case["relevance"]) <= ids

class TestSignalNdcgCases:
    """Signal rerank nDCG — HuggingFace indirme yok."""

    async def test_ortalama_bes_pozitif(self) -> None:
        reranker = SignalReranker()
        rows: list[tuple[list[str], dict[str, float]]] = []
        for case in NDCG_CASES:
            candidates = [
                RetrievalCandidate(
                    chunk_id=str(doc["id"]),
                    content=str(doc["content"]),
                    fused_score=float(doc.get("fused_score", 0.0)),
                )
                for doc in case["docs"]
            ]
            ranked = await reranker.rerank(str(case["query"]), candidates, top_k=10)
            rows.append(([item.chunk_id for item in ranked], case["relevance"]))
        score = mean_ndcg(rows, 5)
        assert 0.0 < score <= 1.0
