"""RAG hattı testleri: chunker, füzyon, reranker, parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.rag.chunker import (
    chunk_document,
    chunk_text,
    code_separators,
    split_markdown_headers,
    _overlap_prefix,
)
from app.services.rag.parsers import (
    ParsedDocument,
    ParsedPage,
    classify,
    html_to_text,
    is_supported,
    parse_file_sync,
    xml_to_text,
)
from app.services.rag.retriever import (
    RetrievalCandidate,
    SignalReranker,
    create_reranker,
    autocut,
    autocut_index,
    cap_per_document,
    cluster_adjacent,
    distribution_based_fusion,
    expand_retrieval_query,
    filename_search_text,
    hybrid_vector_keyword,
    hypothetical_passage,
    keyword_overlap_score,
    lexical_with_title,
    lost_in_the_middle,
    mmr_select,
    reciprocal_rank_fusion,
    stitch_neighbor_text,
)

class TestChunker:
    """Metin parçalama."""

    def test_kisa_metin_tek_parca(self) -> None:
        chunks = chunk_text("Kısa bir metin.", chunk_size=800)
        assert chunks == ["Kısa bir metin."]

    def test_bos_metin_parca_uretmez(self) -> None:
        assert chunk_text("   \n  ") == []

    def test_uzun_metin_bolunur(self) -> None:
        text = "\n\n".join(f"Bu {index}. paragraftır ve biraz uzundur." * 6 for index in range(20))
        chunks = chunk_text(text, chunk_size=400, overlap=50)
        assert len(chunks) > 1
        assert all(chunk.strip() for chunk in chunks)

    def test_parcalar_makul_boyutta(self) -> None:
        text = "Cümle. " * 500
        chunks = chunk_text(text, chunk_size=300, overlap=40)

        assert all(len(chunk) <= 600 for chunk in chunks)

    def test_ortusme_baglami_korur(self) -> None:
        parts = [f"Bölüm{index} içerik metni burada yer alır." for index in range(40)]
        chunks = chunk_text("\n".join(parts), chunk_size=300, overlap=100)
        assert len(chunks) >= 2

    def test_chonkie_overlap_cumle_sinirinda(self) -> None:
        prev = (
            "Kurulum adımı tamamlandı. Whisper modeli yüklendi ve hazır. "
            "Piper Türkçe konuşur."
        )
        piece = _overlap_prefix(prev, 48)
        assert piece.startswith("Whisper") or piece.startswith("Piper")
        assert not piece.startswith("yüklendi")
        assert _overlap_prefix("tek", 10) == "tek"
        left = "Alfa cümlesi burada biter. " * 10
        right = "Beta paragrafı ayrı durur ve uzundur. " * 10
        chunks = chunk_text(left + "\n\n" + right, chunk_size=160, overlap=50, min_chars=0)
        assert len(chunks) >= 2
        assert any(chunk.startswith("Alfa") or chunk.startswith("Beta") for chunk in chunks[1:])

    def test_kod_dosyasi_satir_butunlugunu_korur(self) -> None:
        code = "\n".join(f"def fonksiyon_{index}():\n    return {index}" for index in range(60))
        chunks = chunk_text(code, chunk_size=300, overlap=40, is_code=True)
        assert len(chunks) > 1
        assert all("def" in chunk or "return" in chunk for chunk in chunks)

    def test_langchain_python_def_ayirici(self) -> None:
        assert code_separators("text/x-python")[0] == "\nclass "
        assert code_separators("text/plain") is None
        body = "    return 1\n" * 16
        code = f"def bir():\n{body}\ndef iki():\n{body}"
        chunks = chunk_text(
            code,
            chunk_size=160,
            overlap=0,
            min_chars=0,
            is_code=True,
            mime="text/x-python",
        )
        assert any(chunk.lstrip().startswith("def iki") for chunk in chunks)
        assert not any("def bir" in chunk and "def iki" in chunk for chunk in chunks)
        document = ParsedDocument(
            pages=[ParsedPage(text=code, page=1)],
            mime_type="text/x-python",
            collection="code",
        )
        doc_chunks = chunk_document(document, chunk_size=160, overlap=0, min_chars=0)
        assert any(chunk.content.lstrip().startswith("def iki") for chunk in doc_chunks)

    def test_langchain_js_function_ayirici(self) -> None:
        body = "  return 1;\n" * 16
        code = f"function bir() {{\n{body}}}\nfunction iki() {{\n{body}}}"
        chunks = chunk_text(
            code,
            chunk_size=140,
            overlap=0,
            min_chars=0,
            is_code=True,
            mime="text/javascript",
        )
        assert any(chunk.lstrip().startswith("function iki") for chunk in chunks)

    def test_belge_parcalama_sayfa_bilgisini_korur(self) -> None:
        document = ParsedDocument(
            pages=[
                ParsedPage(text="Birinci sayfa içeriği. " * 40, page=1),
                ParsedPage(text="İkinci sayfa içeriği. " * 40, page=2),
            ]
        )
        chunks = chunk_document(document, chunk_size=200, overlap=20)
        pages = {chunk.page for chunk in chunks}
        assert pages == {1, 2}
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))

    def test_langchain_atx_baslikta_bolum_ayrilir(self) -> None:
        text = (
            "# Kurulum\n\nDocker compose ile ayağa kalkar ve servisler hazır olur.\n\n"
            "# Ses\n\nPiper Türkçe konuşur, Whisper dinler.\n"
        )
        sections = split_markdown_headers(text)
        assert len(sections) == 2
        assert sections[0].startswith("# Kurulum")
        assert "Piper" not in sections[0]
        assert sections[1].startswith("# Ses")
        fenced = "# Dış\n\n```\n# bu kod\n```\n\ndevam eder.\n"
        assert len(split_markdown_headers(fenced)) == 1
        chunks = chunk_text(text, chunk_size=80, overlap=0, min_chars=0, is_markdown=True)
        assert any(c.startswith("# Kurulum") for c in chunks)
        assert any(c.startswith("# Ses") for c in chunks)

    def test_kucuk_parcalar_komsuya_yapistirilir(self) -> None:
        text = "Kısa başlık.\n\n" + ("Bu ikinci paragraf yeterince uzundur. " * 20)
        chunks = chunk_text(text, chunk_size=400, overlap=0, min_chars=80)
        assert not any(chunk.strip() == "Kısa başlık." for chunk in chunks)
        assert any("Kısa başlık" in chunk and len(chunk) >= 80 for chunk in chunks)

class TestWindowAndDiversity:
    """Sentence-window, auto-merge ve MMR."""

    def test_komsu_metin_birlesir(self) -> None:
        joined = stitch_neighbor_text("orta", "önce", "sonra", max_chars=80)
        assert joined == "önce\norta\nsonra"

    def test_bitisik_parcalar_tek_kume(self) -> None:
        candidates = [
            RetrievalCandidate(
                chunk_id="a", document_id="doc", chunk_index=2, content="a", final_score=0.9
            ),
            RetrievalCandidate(
                chunk_id="b", document_id="doc", chunk_index=3, content="b", final_score=0.4
            ),
            RetrievalCandidate(
                chunk_id="c", document_id="other", chunk_index=1, content="c", final_score=0.5
            ),
        ]
        clusters = cluster_adjacent(candidates, gap=1)
        assert len(clusters) == 2
        assert {item.chunk_id for item in clusters[0]} == {"a", "b"}

    def test_mmr_ayni_metni_tekrarlamaz(self) -> None:
        candidates = [
            RetrievalCandidate(
                chunk_id="1", content="Docker compose postgresql servisi", final_score=0.9
            ),
            RetrievalCandidate(
                chunk_id="2",
                content="Docker compose postgresql servisi kurulumu",
                final_score=0.85,
            ),
            RetrievalCandidate(
                chunk_id="3", content="Türkçe Piper ses modeli ayarları", final_score=0.4
            ),
        ]
        picked = mmr_select(candidates, top_k=2, lambda_mult=0.5)
        assert picked[0].chunk_id == "1"
        assert picked[1].chunk_id == "3"

    def test_haystack_lost_in_the_middle_uclari_korur(self) -> None:
        ranked = ["en-iyi", "iki", "uc", "dort"]
        assert lost_in_the_middle(ranked)[0] == "en-iyi"
        assert lost_in_the_middle(ranked)[-1] == "iki"
        assert lost_in_the_middle(["tek"]) == ["tek"]
        assert lost_in_the_middle(["a", "b"]) == ["a", "b"]

    def test_weaviate_autocut_ilk_ucurumda_keser(self) -> None:

        assert autocut_index([2, 1.95, 1.9, 0.2, 0.1, 0.1, -1], 1) == 3
        assert autocut_index([5, 1, 1, 1, 1, 0, 0], 1) == 1
        assert autocut_index([1.0, 0.98, 0.95, 0.9, 0.88, 0.87, 0.80, 0.79], 1) == 3
        assert autocut_index([1.0, 0.98, 0.95, 0.9, 0.88, 0.87, 0.80, 0.79], 2) == 6
        assert autocut_index([0.4, 0.4, 0.4], 1) == 3
        weak = [
            RetrievalCandidate(chunk_id="a", content="güçlü", final_score=0.9),
            RetrievalCandidate(chunk_id="b", content="güçlü-2", final_score=0.85),
            RetrievalCandidate(chunk_id="c", content="zayıf", final_score=0.2),
            RetrievalCandidate(chunk_id="d", content="zayıf-2", final_score=0.1),
        ]
        kept = autocut(weak, jumps=1)
        assert [item.chunk_id for item in kept] == ["a", "b"]

    def test_weaviate_groupby_belge_basina_tavan(self) -> None:
        pool = [
            RetrievalCandidate(chunk_id="a1", document_id="pdf", content="a", final_score=0.9),
            RetrievalCandidate(chunk_id="a2", document_id="pdf", content="b", final_score=0.8),
            RetrievalCandidate(chunk_id="a3", document_id="pdf", content="c", final_score=0.7),
            RetrievalCandidate(chunk_id="b1", document_id="not", content="d", final_score=0.6),
        ]
        kept = cap_per_document(pool, max_per=2)
        assert [item.chunk_id for item in kept] == ["a1", "a2", "b1"]

    def test_sorgu_dolgusu_atilir(self) -> None:
        assert expand_retrieval_query("ekran kartım neydi lütfen") == "ekran kartım"

    def test_hyde_cevap_bicimli_pasaj_uretir(self) -> None:
        passage = hypothetical_passage("Docker nedir")
        assert "Docker" in passage
        assert "tanım" in passage or "açıklama" in passage

    def test_odysseus_kelime_ortusmesi_ayni_vektorden_one_cikarir(self) -> None:
        query = "RTX 5070 ekran kartı"
        plain = hybrid_vector_keyword(0.40, query, "hava güzel güneşli bir gün")
        boosted = hybrid_vector_keyword(
            0.40, query, "Kullanıcının ekran kartı NVIDIA RTX 5070."
        )
        assert keyword_overlap_score(query, "Kullanıcının ekran kartı NVIDIA RTX 5070.") > 0.5
        assert boosted > plain

    def test_ragflow_baslik_alani_dosya_adini_yukseltir(self) -> None:
        query = "RTX 5070"
        content = "kullanıcı notları ve hatırlatmalar"
        assert filename_search_text("klasor/rtx-5070-notlarim.txt") == "rtx 5070 notlarim"
        assert lexical_with_title(query, content, "rtx-5070-notlarim.txt") > lexical_with_title(
            query, content
        )
        titled = hybrid_vector_keyword(0.40, query, content, "rtx-5070-notlarim.txt")
        plain = hybrid_vector_keyword(0.40, query, content)
        assert titled > plain
        matched = "Kullanıcının ekran kartı NVIDIA RTX 5070."
        assert hybrid_vector_keyword(0.40, query, matched, "alisveris.txt") == hybrid_vector_keyword(
            0.40, query, matched
        )

class TestFusion:
    """Reciprocal Rank Fusion."""

    def test_her_iki_listede_olan_ust_sirada(self) -> None:
        dense = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
        sparse = [("c", 5.0), ("a", 3.0)]
        fused = reciprocal_rank_fusion(dense, sparse)
        assert fused["a"] > fused["b"]
        assert fused["c"] > fused["b"]

    def test_bos_listeler(self) -> None:
        assert reciprocal_rank_fusion([], []) == {}

    def test_tek_liste_calisir(self) -> None:
        fused = reciprocal_rank_fusion([("a", 1.0), ("b", 0.5)], [])
        assert fused["a"] > fused["b"]

    def test_haystack_dbsf_olcek_ve_cakismada_max(self) -> None:

        dense = [("a", 0.6), ("b", 0.2), ("c", 0.5)]
        sparse = [("d", 0.5), ("e", 0.8), ("f", 1.1), ("g", 0.3), ("a", 0.3)]
        fused = distribution_based_fusion(dense, sparse)
        assert fused["a"] == pytest.approx(0.66, abs=0.02)
        assert fused["b"] == pytest.approx(0.27, abs=0.02)
        assert fused["c"] == pytest.approx(0.56, abs=0.02)
        assert fused["d"] == pytest.approx(0.44, abs=0.02)
        assert fused["e"] == pytest.approx(0.60, abs=0.02)
        assert fused["f"] == pytest.approx(0.76, abs=0.02)
        assert fused["g"] == pytest.approx(0.33, abs=0.02)
        assert fused["a"] > fused["b"]
        same = distribution_based_fusion([("a", 0.2), ("b", 0.2), ("c", 0.2)], [])
        assert same == {"a": 0.0, "b": 0.0, "c": 0.0}

class TestReranker:
    """Sinyal tabanlı yeniden sıralama."""

    async def test_ilgili_parca_one_cikar(self) -> None:
        candidates = [
            RetrievalCandidate(
                chunk_id="alakasiz",
                content="Bugün hava çok güzel ve güneşli bir gün.",
                fused_score=0.02,
            ),
            RetrievalCandidate(
                chunk_id="alakali",
                content=(
                    "Docker compose ile PostgreSQL servisini başlatmak için up komutu kullanılır."
                ),
                fused_score=0.02,
            ),
        ]
        ranked = await SignalReranker().rerank("docker compose postgresql", candidates, top_k=2)
        assert ranked[0].chunk_id == "alakali"

    async def test_bos_liste(self) -> None:
        assert await SignalReranker().rerank("sorgu", [], top_k=5) == []

    async def test_top_k_sinirlanir(self) -> None:
        candidates = [
            RetrievalCandidate(chunk_id=str(index), content=f"metin {index}", fused_score=0.1)
            for index in range(10)
        ]
        ranked = await SignalReranker().rerank("metin", candidates, top_k=3)
        assert len(ranked) == 3

    async def test_sinyaller_hesaplanir(self) -> None:
        candidates = [RetrievalCandidate(chunk_id="a", content="python kodu", fused_score=0.1)]
        ranked = await SignalReranker().rerank("python", candidates, top_k=1)
        assert set(ranked[0].signals) == {"fusion", "coverage", "proximity", "density"}

class _FakeCrossEncoder:
    """HF indirmeden skor üretir."""

    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] | None = None
        self.device = "cpu"

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.pairs = list(pairs)
        scores: list[float] = []
        for _query, passage in pairs:
            lowered = passage.casefold()
            scores.append(9.0 if "postgresql" in lowered or "docker" in lowered else 0.1)
        return scores

class TestCrossEncoderReranker:
    """bge-reranker-v2-m3 sözleşmesi; gerçek model pytest'te yok."""

    async def test_skora_gore_siralar(self) -> None:
        from app.services.rag.retriever import CrossEncoderReranker

        candidates = [
            RetrievalCandidate(
                chunk_id="alakasiz",
                content="Bugün hava çok güzel ve güneşli bir gün.",
                fused_score=0.9,
            ),
            RetrievalCandidate(
                chunk_id="alakali",
                content="Docker compose ile PostgreSQL servisini başlatmak için up kullanılır.",
                fused_score=0.1,
            ),
        ]
        ranked = await CrossEncoderReranker(encoder=_FakeCrossEncoder()).rerank(
            "docker compose postgresql", candidates, top_k=2
        )
        assert ranked[0].chunk_id == "alakali"
        assert ranked[0].signals.get("cross", 0) > ranked[1].signals.get("cross", 0)

    async def test_bos_liste(self) -> None:
        from app.services.rag.retriever import CrossEncoderReranker

        assert await CrossEncoderReranker(encoder=_FakeCrossEncoder()).rerank("q", [], 5) == []

    async def test_top_k_sinirlanir(self) -> None:
        from app.services.rag.retriever import CrossEncoderReranker

        candidates = [
            RetrievalCandidate(chunk_id=str(index), content=f"metin {index}", fused_score=0.1)
            for index in range(10)
        ]
        ranked = await CrossEncoderReranker(encoder=_FakeCrossEncoder()).rerank(
            "metin", candidates, 3
        )
        assert len(ranked) == 3

    async def test_predict_hatasi_sinyale_dusar(self) -> None:
        from app.services.rag.retriever import CrossEncoderReranker

        class Boom:
            def predict(self, pairs: object) -> list[float]:
                raise RuntimeError("model yok")

        candidates = [
            RetrievalCandidate(
                chunk_id="alakasiz",
                content="Bugün hava çok güzel ve güneşli bir gün.",
                fused_score=0.02,
            ),
            RetrievalCandidate(
                chunk_id="alakali",
                content=(
                    "Docker compose ile PostgreSQL servisini başlatmak için up komutu kullanılır."
                ),
                fused_score=0.02,
            ),
        ]
        ranked = await CrossEncoderReranker(encoder=Boom(), fallback=SignalReranker()).rerank(
            "docker compose postgresql", candidates, top_k=2
        )
        expected = await SignalReranker().rerank(
            "docker compose postgresql",
            [
                RetrievalCandidate(
                    chunk_id="alakasiz",
                    content="Bugün hava çok güzel ve güneşli bir gün.",
                    fused_score=0.02,
                ),
                RetrievalCandidate(
                    chunk_id="alakali",
                    content=(
                        "Docker compose ile PostgreSQL servisini başlatmak için up komutu kullanılır."
                    ),
                    fused_score=0.02,
                ),
            ],
            top_k=2,
        )
        assert ranked[0].chunk_id == expected[0].chunk_id

    async def test_load_fail_sinyale_dusar(self) -> None:
        from app.services.rag.retriever import CrossEncoderReranker

        def boom() -> object:
            raise OSError("huggingface offline")

        candidates = [
            RetrievalCandidate(chunk_id="a", content="python kodu", fused_score=0.1),
        ]
        reranker = CrossEncoderReranker(fallback=SignalReranker(), loader=boom)
        ranked = await reranker.rerank("python", candidates, top_k=1)
        assert ranked[0].chunk_id == "a"
        assert "coverage" in ranked[0].signals
        assert reranker.using_fallback is True

class TestCreateReranker:
    """Factory: ayar + yükleme hatası."""

    def test_kapaliysa_sinyal(self) -> None:
        from app.core.config import Settings

        settings = Settings(rag_rerank_enabled=False)
        assert isinstance(create_reranker(settings), SignalReranker)

    def test_aciksa_cross_encoder(self) -> None:
        from app.core.config import Settings
        from app.services.rag.retriever import CrossEncoderReranker

        settings = Settings(rag_rerank_enabled=True)
        assert isinstance(create_reranker(settings), CrossEncoderReranker)

    def test_varsayilan_model_cpu_ve_dim_384(self) -> None:
        from app.core.config import Settings

        settings = Settings(
            embedding_dim=384,
            embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            rag_rerank_model="BAAI/bge-reranker-v2-m3",
            rag_rerank_device="cpu",
        )
        assert settings.embedding_dim == 384
        assert settings.rag_rerank_model == "BAAI/bge-reranker-v2-m3"
        assert settings.rag_rerank_device == "cpu"
        assert "minilm" in settings.embedding_model.lower()

class TestRAGServiceRerankerDI:
    def test_enjekte_edilen_reranker_kullanilir(self, container) -> None:
        from app.services.rag.service import RAGService

        class Spy:
            def __init__(self) -> None:
                self.calls = 0

            async def rerank(self, query, candidates, top_k):
                self.calls += 1
                return candidates[:top_k]

        spy = Spy()
        rag = RAGService(
            container.settings,
            container.database,
            container.vector_store,
            container.embeddings,
            reranker=spy,
        )
        assert rag._reranker is spy

class TestParsers:
    """Dosya ayrıştırma."""

    def test_desteklenen_uzantilar(self) -> None:
        for name in (
            "a.pdf",
            "b.docx",
            "c.txt",
            "d.md",
            "e.json",
            "f.csv",
            "g.py",
            "h.ts",
            "i.sql",
            "j.log",
        ):
            assert is_supported(name), name

    def test_desteklenmeyen_uzanti(self) -> None:
        assert not is_supported("video.mp4")
        assert not is_supported("resim.png")

    def test_kod_dosyalari_code_collection(self) -> None:
        assert classify("main.py")[0] == "code"
        assert classify("app.tsx")[0] == "code"
        assert classify("rapor.pdf")[0] == "documents"

    def test_metin_dosyasi_okunur(self, tmp_path: Path) -> None:
        target = tmp_path / "not.txt"
        target.write_text("Türkçe içerik: ğüşiöç", encoding="utf-8")
        parsed = parse_file_sync(target)
        assert "Türkçe içerik" in parsed.full_text
        assert parsed.error is None

    def test_json_dosyasi_bicimlendirilir(self, tmp_path: Path) -> None:
        target = tmp_path / "veri.json"
        target.write_text('{"ad":"Uryx","surum":1}', encoding="utf-8")
        parsed = parse_file_sync(target)
        assert '"ad"' in parsed.full_text
        assert "Uryx" in parsed.full_text

    def test_html_script_ve_etiket_dokulur(self, tmp_path: Path) -> None:
        raw = (
            "<html><head><title>Gizli</title>"
            "<script>alert('xss')</script><style>p{color:red}</style></head>"
            "<body><h1>Kurulum</h1><p>Docker &amp; Piper çalışır.</p></body></html>"
        )
        text = html_to_text(raw)
        assert "alert" not in text
        assert "color:red" not in text
        assert "Gizli" not in text
        assert "<p>" not in text
        assert "Kurulum" in text
        assert "# Kurulum" in text
        assert "Docker & Piper" in text
        target = tmp_path / "sayfa.html"
        target.write_text(raw, encoding="utf-8")
        parsed = parse_file_sync(target)
        assert parsed.mime_type == "text/html"
        assert parsed.collection == "documents"
        assert "Kurulum" in parsed.full_text
        assert "alert" not in parsed.full_text
        assert classify("not.htm") == ("documents", "text/html")
        assert is_supported("not.htm")

    def test_langchain_html_baslik_atx_bolum(self) -> None:
        html = (
            "<html><body>"
            "<h1>Kurulum</h1><p>Docker compose ile ayağa kalkar ve servisler hazır olur.</p>"
            "<h1>Ses</h1><p>Piper Türkçe konuşur, Whisper dinler.</p>"
            "</body></html>"
        )
        text = html_to_text(html)
        sections = split_markdown_headers(text)
        assert len(sections) == 2
        assert sections[0].startswith("# Kurulum")
        assert "Piper" not in sections[0]
        assert sections[1].startswith("# Ses")
        document = ParsedDocument(
            pages=[ParsedPage(text=text, page=1)],
            mime_type="text/html",
            collection="documents",
        )
        chunks = chunk_document(document, chunk_size=80, overlap=0, min_chars=0)
        assert any(chunk.content.startswith("# Kurulum") for chunk in chunks)
        assert any(chunk.content.startswith("# Ses") for chunk in chunks)

    def test_unstructured_xml_etiket_dokulur(self, tmp_path: Path) -> None:
        raw = (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<note><title>Kurulum</title><body>Docker &amp; Piper</body></note>"
        )
        text = xml_to_text(raw)
        assert "<title>" not in text
        assert "Kurulum" in text
        assert "Docker & Piper" in text
        xxe = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///no-such-uryx-xxe">]>'
            "<x>&e;gizli</x>"
        )
        leaked = xml_to_text(xxe)
        assert "no-such-uryx-xxe" not in leaked
        target = tmp_path / "not.xml"
        target.write_text(raw, encoding="utf-8")
        parsed = parse_file_sync(target)
        assert parsed.mime_type == "application/xml"
        assert "Kurulum" in parsed.full_text
        assert "<body>" not in parsed.full_text
        assert parsed.error is None

    def test_csv_dosyasi_satirlara_donusur(self, tmp_path: Path) -> None:
        target = tmp_path / "tablo.csv"
        target.write_text("ad,yas\nAli,30\nAyse,25\n", encoding="utf-8")
        parsed = parse_file_sync(target)
        assert "ad: Ali" in parsed.full_text
        assert "yas: 25" in parsed.full_text

    def test_bozuk_dosya_hata_dondurur_ama_cokmez(self, tmp_path: Path) -> None:
        target = tmp_path / "bozuk.pdf"
        target.write_bytes(b"bu gecerli bir pdf degil")
        parsed = parse_file_sync(target)
        assert parsed.error is not None
        assert parsed.is_empty

class TestPdfOcr:
    """Taranmış PDF: RapidOCR; gerçek ONNX pytest'te yok."""

    def _blank_pdf(self, tmp_path: Path) -> Path:
        from pypdf import PdfWriter

        path = tmp_path / "scan.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(path)
        return path

    def test_sayfa_metni_varsa_ocr_atlanir(self) -> None:
        from app.services.rag.parsers import pdf_page_text

        class Page:
            def extract_text(self) -> str:
                return "Merhaba Uryx"

        calls = {"n": 0}

        def ocr(_page: object, _number: int) -> str:
            calls["n"] += 1
            return "OCR_KACAK"

        assert pdf_page_text(Page(), 1, ocr_page=ocr) == "Merhaba Uryx"
        assert calls["n"] == 0

    def test_taranmis_pdf_ocr_metin_alir(self, tmp_path: Path) -> None:
        from app.services.rag.parsers import _parse_pdf

        path = self._blank_pdf(tmp_path)
        parsed = _parse_pdf(
            path,
            "documents",
            "application/pdf",
            ocr_page=lambda _page, _number: "Fatura tutarı 120 TL",
        )
        assert not parsed.is_empty
        assert "Fatura" in parsed.full_text
        assert parsed.error is None

    def test_ocr_bos_kalirsa_desteklenmiyor_demez(self, tmp_path: Path) -> None:
        from app.services.rag.parsers import _parse_pdf

        path = self._blank_pdf(tmp_path)
        parsed = _parse_pdf(
            path, "documents", "application/pdf", ocr_page=lambda _page, _number: ""
        )
        assert parsed.is_empty
        assert parsed.error is not None
        assert "OCR desteklenmiyor" not in parsed.error

    def test_rapidocr_sonuc_metne_doner(self) -> None:
        from app.services.rag.parsers import _rapidocr_result_text

        class Out:
            txts = ["Merhaba", "Uryx"]

        assert "Merhaba" in _rapidocr_result_text(Out())
        assert "fatura" in _rapidocr_result_text([[None, "fatura"], [None, "120"]]).lower()

class TestRAGService:
    """RAG servisi uçtan uca (Qdrant olmadan)."""

    async def test_desteklenmeyen_dosya_reddedilir(self, container) -> None:
        import pytest
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            await container.rag.ingest_upload("video.mp4", b"veri")

    async def test_yukleme_ve_indeksleme(self, container, tmp_path: Path) -> None:
        container.settings.upload_dir = str(tmp_path)

        content = ("Uryx yerel çalışan bir yapay zekâ asistanıdır. " * 30).encode("utf-8")
        result = await container.rag.ingest_upload("hakkinda.txt", content)
        assert result["duplicate"] is False

        await container.rag.process_document(result["document_id"])

        stats = await container.rag.stats()
        assert stats["total"] == 1
        assert stats["total_chunks"] > 0

        hits = await container.rag.search("yapay zekâ asistanı", top_k=3)
        assert hits, "Metin araması sonuç döndürmeli"

    async def test_retrieve_komsu_parcalari_diker(self, container, tmp_path: Path) -> None:
        container.settings.upload_dir = str(tmp_path)
        container.settings.rag_chunk_size = 90
        container.settings.rag_chunk_overlap = 0
        container.settings.rag_min_chunk_chars = 0
        container.settings.rag_neighbor_window = 1
        container.settings.rag_min_score = 0.0
        text = (
            "ALFA_BOLUM birinci paragraf buradadir ve yeterince uzundur aslinda.\n\n"
            "BETA_ANAHTAR ikinci paragraf arama hedefidir ve yeterince uzundur.\n\n"
            "GAMA_SONUC ucuncu paragraf komsu olarak gelmelidir yeterince.\n\n"
            "DELTA_SON dorduncu paragraf ayri kalabilir ve yeterince uzundur.\n"
        )
        result = await container.rag.ingest_upload("komsu.txt", text.encode("utf-8"))
        await container.rag.process_document(result["document_id"])
        hits = await container.rag.search("BETA_ANAHTAR", top_k=1)
        assert hits
        assert "BETA_ANAHTAR" in hits[0].content
        assert "ALFA_BOLUM" in hits[0].content or "GAMA_SONUC" in hits[0].content

    async def test_yinelenen_dosya_tespit_edilir(self, container, tmp_path: Path) -> None:
        container.settings.upload_dir = str(tmp_path)
        content = b"Ayni icerik"

        first = await container.rag.ingest_upload("a.txt", content)
        second = await container.rag.ingest_upload("b.txt", content)

        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert second["document_id"] == first["document_id"]
