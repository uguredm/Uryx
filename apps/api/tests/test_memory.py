"""Hafıza sistemi ve memory evaluator testleri."""

from __future__ import annotations

import json

import pytest
from app.db.models import MemoryCategory, MessageRole
from app.db.repositories.conversation import ConversationRepository, MessageRepository
from app.services.memory.episodes import compact_turns, summarize_turns
from app.services.memory.evaluator import MemoryEvaluator, _parse_json_object
from app.services.memory.ranking import (
    adjust_recency,
    diversify_memory_hits,
    entity_overlap,
    extract_entities,
    rank_memory,
    recency_score,
    score_episode,
    temporal_intent,
)

class TestPreFilter:
    """LLM'e gitmeden önce çalışan ön filtre."""

    @pytest.mark.parametrize(
        "message",
        ["selam", "Merhaba", "teşekkürler", "tamam", "ok", "günaydın", "iyi geceler", "evet"],
    )
    def test_selamlasma_elenir(self, message: str) -> None:
        assert MemoryEvaluator.is_trivial(message) is True

    def test_cok_kisa_mesaj_elenir(self) -> None:
        assert MemoryEvaluator.is_trivial("naber") is True

    def test_anlamli_mesaj_gecer(self) -> None:
        assert (
            MemoryEvaluator.is_trivial(
                "Projelerimi C:\\Users\\ben\\Desktop\\Projeler klasöründe tutuyorum."
            )
            is False
        )

    def test_acik_hatirlama_talebi_on_filtreyi_atlar(self) -> None:

        assert MemoryEvaluator.is_trivial("Bunu hatırla") is False

class TestSensitiveFilter:
    """Hassas veri filtresi."""

    @pytest.mark.parametrize(
        "text",
        [
            "şifrem: Abc12345!",
            "parola = gizli123",
            "API key: sk-abcdefghijklmnopqrstuvwx",
            "token=ghp_abcdefghijklmnopqrstuvwxyz1234",
            "HF token hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "kart numaram 4111 1111 1111 1111",
            "TC kimlik 12345678901",
            "-----BEGIN RSA PRIVATE KEY-----",
        ],
    )
    def test_hassas_metinler_yakalanir(self, text: str) -> None:
        assert MemoryEvaluator.contains_sensitive(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "RTX 5070 ekran kartım var.",
            "Kod yazarken 4 boşluk girinti tercih ediyorum.",
            "Projelerim Masaüstü/Projeler klasöründe.",
        ],
    )
    def test_normal_metinler_gecer(self, text: str) -> None:
        assert MemoryEvaluator.contains_sensitive(text) is False

class TestDurabilityFilter:
    """Kalıcılık filtresi — küçük modellerin ürettiği çöp adaylar."""

    @pytest.mark.parametrize(
        "content",
        [
            "Proje yapısı ve kritik bilgiler kalıcı hafızama kaydedildi.",
            "Kullanıcının hbs klasörünü tarayıp yapısını incelediğim için bu bilgi "
            "kalıcı hafızama kaydedildi.",
            "Docker entegrasyonu ve veri işleme detayları kaydedildi.",
        ],
    )
    def test_kendi_kayit_eylemini_anlatan_adaylar_elenir(self, content: str) -> None:
        assert MemoryEvaluator.is_self_referential(content) is True
        assert MemoryEvaluator.rejection_reason(content) is not None

    @pytest.mark.parametrize(
        "content",
        [
            "Spotify'da son çalınan şarkıyı açmak istiyor.",
            "Spotify uygulamasında son şarkıyı aç",
            "Masaüstündeki dosyaları listele",
        ],
    )
    def test_tek_seferlik_istekler_elenir(self, content: str) -> None:
        assert MemoryEvaluator.rejection_reason(content) is not None

    @pytest.mark.parametrize(
        "content",
        [
            "Yapay zeka geliştirmek için büyük miktarda, temiz ve etik veri gerekir.",
            "Node.js, modern web için ideal bir araç olmasına rağmen, bazı durumlarda "
            "alternatif dil tercihi gerekebilir.",
            "İSKİ genel müdürünün 2026 yılında Şafak Başa olduğu belirlendi.",
        ],
    )
    def test_kullaniciya_baglanmayan_genel_bilgi_elenir(self, content: str) -> None:
        assert MemoryEvaluator.rejection_reason(content) is not None

    @pytest.mark.parametrize(
        "content",
        [
            "Kullanıcının ismi Uğur Samet Erdem ve ünvanı şef.",
            "Kullanıcının bilgisayarında NVIDIA RTX 5070 ekran kartı var.",
            "Kullanıcı kod yazarken 4 boşluk girinti tercih ediyor.",
            "Uryx projesinde servisler Docker Compose ile ayağa kaldırılır.",
            "Kullanıcı sabah kalkınca Spotify'ı açar.",
            "Kullanıcı cevapların Türkçe yazılmasını ister.",
            "Kullanıcının bilgisayarında Windows 11 kurulu olduğu tespit edildi.",
        ],
    )
    def test_kalici_bilgiler_korunur(self, content: str) -> None:
        assert MemoryEvaluator.rejection_reason(content) is None

    async def test_cop_adaylar_degerlendirmede_kaydedilmez(self, fake_llm) -> None:
        fake_llm.completion_json = json.dumps(
            {
                "should_save": True,
                "reason": "model kaydetmek istedi",
                "candidates": [
                    {
                        "content": "Proje yapısı ve kritik bilgiler kalıcı hafızama kaydedildi.",
                        "category": "project",
                        "importance": 1.0,
                    },
                    {
                        "content": "Spotify'da son çalınan şarkıyı açmak istiyor.",
                        "category": "preference",
                        "importance": 0.9,
                    },
                ],
            }
        )
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate("Spotify'da son şarkıyı aç", "Açıyorum.")
        assert outcome.should_save is False

    async def test_cop_ayiklanirken_saglam_aday_kalir(self, fake_llm) -> None:
        fake_llm.completion_json = json.dumps(
            {
                "should_save": True,
                "reason": "iki aday",
                "candidates": [
                    {"content": "Bu bilgi kalıcı hafızama kaydedildi.", "category": "other"},
                    {
                        "content": "Kullanıcının ismi Uğur Samet Erdem.",
                        "category": "contact",
                        "importance": 0.9,
                    },
                ],
            }
        )
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Benim adım Uğur Samet Erdem.", "Tanıştığımıza sevindim."
        )
        assert outcome.should_save is True
        assert len(outcome.candidates) == 1
        assert outcome.candidates[0].category is MemoryCategory.CONTACT

class TestJsonParsing:
    """Evaluator çıktısının ayrıştırılması."""

    def test_duz_json(self) -> None:
        assert _parse_json_object('{"should_save": true}') == {"should_save": True}

    def test_kod_bloklu_json(self) -> None:
        raw = '```json\n{"should_save": false, "reason": "önemsiz"}\n```'
        parsed = _parse_json_object(raw)
        assert parsed is not None
        assert parsed["should_save"] is False

    def test_metin_icine_gomulu_json(self) -> None:
        raw = 'Değerlendirmem şu: {"should_save": true, "candidates": []} — bitti.'
        parsed = _parse_json_object(raw)
        assert parsed is not None
        assert parsed["should_save"] is True

    def test_gecersiz_json_none_doner(self) -> None:
        assert _parse_json_object("bu bir json değil") is None

class TestEvaluatorFlow:
    """Uçtan uca değerlendirme akışı."""

    async def test_onemsiz_konusma_kaydedilmez(self, fake_llm) -> None:
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate("selam", "Merhaba!")
        assert outcome.should_save is False
        assert not fake_llm.calls, "Ön filtre LLM'i çağırmamalı"

    async def test_hassas_mesaj_llm_e_gitmez(self, fake_llm) -> None:
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Sunucu şifrem Abc12345! olarak ayarlandı, not al", "Tamam."
        )
        assert outcome.should_save is False
        assert not fake_llm.calls

    async def test_gecerli_aday_kabul_edilir(self, fake_llm) -> None:
        fake_llm.completion_json = json.dumps(
            {
                "should_save": True,
                "reason": "Donanım bilgisi",
                "candidates": [
                    {
                        "content": "Kullanıcının ekran kartı NVIDIA RTX 5070 12 GB.",
                        "category": "system_info",
                        "importance": 0.8,
                        "tags": ["donanım"],
                    }
                ],
            }
        )
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Bilgisayarımda RTX 5070 12 GB ekran kartı var, bunu bil.", "Not aldım."
        )

        assert outcome.should_save is True
        assert len(outcome.candidates) == 1
        assert outcome.candidates[0].category is MemoryCategory.SYSTEM_INFO
        assert outcome.candidates[0].importance == 0.8

    async def test_hassas_aday_son_filtrede_elenir(self, fake_llm) -> None:
        fake_llm.completion_json = json.dumps(
            {
                "should_save": True,
                "reason": "test",
                "candidates": [
                    {
                        "content": "Kullanıcının API key'i sk-abcdefghijklmnopqrstu",
                        "category": "fact",
                    }
                ],
            }
        )
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Şu bilgiyi kaydet: bilgisayarımın adı URYX-PC", "Tamam."
        )
        assert outcome.should_save is False

    async def test_bozuk_json_ipucu_yoksa_kaydetmez(self, fake_llm) -> None:
        fake_llm.completion_json = "üzgünüm, karar veremedim"
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Projeler klasöründeki dosyaları şimdi listele lütfen.", "Tamam."
        )
        assert outcome.should_save is False

    async def test_bozuk_json_hatirla_ipucu_kaydeder(self, fake_llm) -> None:
        fake_llm.completion_json = "üzgünüm, karar veremedim"
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Sık kullandığım klasör Masaüstü/Projeler, bunu hatırla.", "Tamam."
        )
        assert outcome.should_save is True
        assert outcome.candidates[0].category is MemoryCategory.FACT

    async def test_bozuk_json_donanim_ipucu_kaydeder(self, fake_llm) -> None:
        fake_llm.completion_json = "geçersiz"
        evaluator = MemoryEvaluator(fake_llm)
        outcome = await evaluator.evaluate(
            "Bilgisayarımda RTX 5070 12 GB ekran kartı var.", "Not aldım."
        )
        assert outcome.should_save is True
        assert "RTX 5070" in outcome.candidates[0].content

class TestMemoryService:
    """Hafıza servisi CRUD."""

    async def test_kayit_olustur_ve_listele(self, container) -> None:
        memory = await container.memory.create(
            "Kullanıcı Türkçe cevap tercih ediyor.",
            category=MemoryCategory.PREFERENCE,
            importance=0.9,
        )
        assert memory.id

        records = await container.memory.list()
        assert len(records) == 1
        assert records[0].content.startswith("Kullanıcı Türkçe")

    async def test_yinelenen_kayit_eklenmez(self, container) -> None:
        text = "Kullanıcının işletim sistemi Windows 11."
        first = await container.memory.create(text)
        second = await container.memory.create(text)
        assert first.id == second.id
        assert len(await container.memory.list()) == 1

    async def test_sabitleme_ve_silme(self, container) -> None:
        memory = await container.memory.create("VS Code kullanıyor.")
        await container.memory.set_pinned(memory.id, True)

        records = await container.memory.list()
        assert records[0].pinned is True

        assert await container.memory.delete(memory.id) is True
        assert await container.memory.list() == []

    async def test_recall_sabitlenmisleri_getirir(self, container) -> None:
        memory = await container.memory.create("Kullanıcının adı Ugur.", pinned=True)
        refs = await container.memory.recall("kullanıcı kim")
        assert any(ref.id == memory.id for ref in refs)

    async def test_recall_varlik_eslesen_kaydi_getirir(self, container) -> None:
        await container.memory.create("Kullanıcı kahveyi şekersiz içer.", importance=0.9)
        gpu = await container.memory.create(
            "Kullanıcının ekran kartı NVIDIA RTX 5070.", importance=0.4
        )
        refs = await container.memory.recall("RTX 5070 ekran kartım neydi")
        assert any(ref.id == gpu.id or "RTX" in ref.content for ref in refs)

    async def test_recall_cekirdek_onemli_kaydi_her_turda_tutar(self, container) -> None:
        core = await container.memory.create(
            "Kullanıcının adı Uğur Samet Erdem.",
            category=MemoryCategory.CONTACT,
            importance=0.95,
        )
        await container.memory.create(
            "Kullanıcı kahveyi şekersiz içer.",
            category=MemoryCategory.PREFERENCE,
            importance=0.4,
        )
        refs = await container.memory.recall("hava nasıl")
        assert any(ref.id == core.id for ref in refs)

class TestRankingAndEpisodes:
    """Mem0 sıralama sinyalleri ve Letta bölüm özeti."""

    def test_tazelik_yari_omurde_yarimlanir(self) -> None:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        assert recency_score(now, now=now) == 1.0
        half = recency_score(now - timedelta(days=14), now=now, half_life_days=14)
        assert 0.45 <= half <= 0.55

    def test_varlik_eslesmesi_skoru_yukseltir(self) -> None:
        entities = extract_entities('Uğur RTX 5070 kartını "Uryx" ile kullanıyor')
        assert any("RTX" in item or "5070" in item for item in entities)
        matched = entity_overlap(["RTX", "5070"], "Kullanıcının ekran kartı NVIDIA RTX 5070.")
        missed = entity_overlap(["RTX", "5070"], "Kullanıcı kahveyi şekersiz içer.")
        assert matched > missed
        boosted = rank_memory(0.5, 0.5, 0.5, entity=1.0)
        plain = rank_memory(0.5, 0.5, 0.5, entity=0.0)
        assert boosted > plain

    def test_zamansal_niyet_tazeligi_cevirir(self) -> None:
        assert temporal_intent("şimdi hangi kartım var") == "current"
        assert temporal_intent("dün ne demiştim") == "past"
        assert adjust_recency(0.2, "current") > 0.2
        assert adjust_recency(0.9, "past") < 0.3

    def test_bolum_ozeti_son_turlari_korur(self) -> None:
        turns = [
            ("user", "selam"),
            ("assistant", "Merhaba"),
            ("user", "Projelerimi Masaüstü/Uryx klasöründe tutuyorum."),
            ("assistant", "Not aldım."),
            ("user", "Ekran kartım RTX 5070."),
            ("assistant", "Kaydettim."),
        ]
        summary = compact_turns(turns, keep_recent=2, max_chars=400)
        assert "RTX 5070" in summary
        assert "Masaüstü/Uryx" in summary
        assert "selam" not in summary.lower()

    async def test_llm_ozeti_kullanilir(self) -> None:
        from tests.conftest import FakeLLM

        turns = [
            ("user", "Projelerimi Masaüstü/Uryx klasöründe tutuyorum."),
            ("assistant", "Not aldım."),
            ("user", "Ekran kartım RTX 5070."),
            ("assistant", "Kaydettim."),
        ]
        llm = FakeLLM()
        llm.reply = "Kullanıcı projelerini Masaüstü/Uryx’te tutar; ekran kartı RTX 5070."
        text = await summarize_turns(turns, llm)
        assert "RTX 5070" in text
        assert "Kaydettim" not in text
        assert llm.calls

    async def test_llm_hatasi_compact_turns(self) -> None:
        turns = [
            ("user", "Projelerimi Masaüstü/Uryx klasöründe tutuyorum."),
            ("assistant", "Not aldım."),
            ("user", "Ekran kartım RTX 5070."),
            ("assistant", "Kaydettim."),
        ]

        class Boom:
            async def complete(self, *args, **kwargs):
                raise RuntimeError("llm kapalı")

        text = await summarize_turns(turns, Boom())  # type: ignore[arg-type]
        assert text == compact_turns(turns)

    async def test_evaluator_json_compact_turns(self) -> None:
        from tests.conftest import FakeLLM

        turns = [
            ("user", "Projelerimi Masaüstü/Uryx klasöründe tutuyorum."),
            ("assistant", "Not aldım."),
            ("user", "Ekran kartım RTX 5070."),
            ("assistant", "Kaydettim."),
        ]
        llm = FakeLLM()
        llm.completion_json = '{"should_save": false, "candidates": []}'
        text = await summarize_turns(turns, llm)
        assert text == compact_turns(turns)

    async def test_index_episode_llm_ozet_yazar(self, container, fake_llm) -> None:
        fake_llm.reply = "Kullanıcı RTX 5070 kullanır ve projeler Uryx klasöründedir."
        fake_llm.completion_json = None
        async with container.database.session() as session:
            conversation = await ConversationRepository(session).create("Kart")
            await MessageRepository(session).create(
                conversation.id,
                MessageRole.USER,
                "Projelerimi Masaüstü/Uryx klasöründe tutuyorum.",
            )
            await MessageRepository(session).create(
                conversation.id, MessageRole.ASSISTANT, "Not aldım."
            )
            await MessageRepository(session).create(
                conversation.id, MessageRole.USER, "Ekran kartım RTX 5070."
            )
            await MessageRepository(session).create(
                conversation.id, MessageRole.ASSISTANT, "Kaydettim."
            )
            conversation_id = conversation.id

        summary = await container.memory.index_episode(conversation_id)
        assert summary is not None
        assert "RTX 5070" in summary
        assert "Kaydettim" not in summary

    def test_bolum_skoru_varlik_eslesen_ozeti_yukseltir(self) -> None:
        hit = score_episode("RTX 5070 kartım neydi", "Kullanıcı: Ekran kartım RTX 5070.")
        miss = score_episode("RTX 5070 kartım neydi", "Kullanıcı kahveyi şekersiz içer.")
        assert hit > miss
        assert hit > 0
        assert score_episode("RTX 5070", "kahve çay su") == 0.0

    def test_langchain_mmr_benzer_hafiza_cesitlenir(self) -> None:
        hits = [
            ("a", "Docker compose postgresql servisi", 0.9),
            ("b", "Docker compose postgresql servisi kurulumu", 0.85),
            ("c", "Türkçe Piper ses modeli ayarları", 0.4),
        ]
        picked = diversify_memory_hits(hits, 2)
        ids = [item_id for item_id, _score in picked]
        assert ids[0] == "a"
        assert "c" in ids
        assert "b" not in ids
        assert diversify_memory_hits([], 3) == []

    async def test_recall_ozet_list_with_summaries_yedekten_getirir(self, container) -> None:
        """Qdrant kapalı + mesajda kelime yok → yalnız özet satırı bulunur."""
        async with container.database.session() as session:
            conversation = await ConversationRepository(session).create("Yeni sohbet")
            await MessageRepository(session).create(
                conversation.id, MessageRole.USER, "tamam peki not aldım"
            )
            await MessageRepository(session).create(
                conversation.id, MessageRole.ASSISTANT, "Anladım."
            )
            await ConversationRepository(session).set_summary(
                conversation.id, "Kullanıcı: Ekran kartım NVIDIA RTX 5070."
            )
            conversation_id = conversation.id

        refs = await container.memory.recall("RTX 5070 ekran kartım neydi")
        assert any(
            ref.id == conversation_id
            and ref.category == "conversation"
            and "RTX 5070" in ref.content
            for ref in refs
        )

    async def test_evaluate_kaydetmese_bile_bolum_ozeti_yazar(self, container, fake_llm) -> None:
        fake_llm.completion_json = '{"should_save": false, "candidates": []}'
        async with container.database.session() as session:
            conversation = await ConversationRepository(session).create("Yeni sohbet")
            await MessageRepository(session).create(
                conversation.id,
                MessageRole.USER,
                "Projelerimi Masaüstü/Uryx klasöründe tutuyorum.",
            )
            await MessageRepository(session).create(
                conversation.id, MessageRole.ASSISTANT, "Not aldım."
            )
            conversation_id = conversation.id

        created = await container.memory.evaluate_and_store(
            "selam", "Merhaba", conversation_id=conversation_id
        )
        assert created == []
        async with container.database.session() as session:
            stored = await ConversationRepository(session).get(conversation_id)
            listed = await ConversationRepository(session).list_with_summaries(limit=10)
        assert stored is not None
        assert stored.summary
        assert "Uryx" in stored.summary
        assert any(item.id == conversation_id for item in listed)
