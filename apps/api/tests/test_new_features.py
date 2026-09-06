"""Ses, web araması ve kullanıcı onayı entegrasyonları."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.errors import LLMUnavailableError
from app.schemas.chat import ChatOptions
from app.services.chat.orchestrator import (
    _browser_open_requested,
    _direct_action_response,
    _direct_retrieval_response,
    _direct_social_response,
    _estimate_tokens,
    _filter_tool_schemas,
    _fit_tools_to_context,
    _fresh_web_lookup_requested,
    _generation_max_tokens,
    _guard_tool_calls,
    _image_search_requested,
    _image_search_subject,
    _instagram_login_wall,
    _latest_media_requested,
    _liked_spotify_requested,
    _media_control_action,
    _media_open_requested,
    _media_search_query,
    _memory_worthy_turn,
    _select_media_url,
    _select_tool_categories,
    _should_skip_thinking,
    _wants_memory_context,
    _wants_rag_context,
    _social_post_requested,
    _spotify_kind,
    _spotify_library_play_requested,
    _tool_schema_tokens,
    _trim_messages_for_context,
    _video_search_requested,
)
from app.services.llm.base import ChatMessage, StreamDelta
from app.services.llm.hybrid_client import HybridLLMClient
from app.services.tts.client import SentenceBuffer, _clean_for_speech
from app.services.web.search import (
    _instagram_post_urls_from_html,
    _rank_social_coverage,
    _resolve_instagram_profile,
    _social_search_subject,
    _video_search_subject,
    _youtube_video_id,
)

class CapturingTTS:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def synthesize(self, text: str, **kwargs: Any) -> bytes:
        self.calls.append({"text": text, **kwargs})
        return b"wav"

class FakeWebSearch:
    async def search(self, query: str, *, max_results: int, **_kwargs: object) -> list[dict[str, str]]:
        return [{"title": query, "summary": "özet", "url": "https://example.com"}][:max_results]

    async def image_search(self, query: str, *, max_results: int) -> list[dict[str, str | int]]:
        return [
            {
                "title": query,
                "image": "https://example.com/image.jpg",
                "thumbnail": "https://example.com/thumb.jpg",
                "source": "https://example.com/page",
                "width": 1200,
                "height": 800,
            }
        ][:max_results]

    async def research(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        return [
            {
                "title": query,
                "summary": "çok kaynaklı özet",
                "url": "https://example.com/research",
                "domain": "example.com",
            }
        ][:max_results]

    async def video_search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        return [
            {
                "title": query,
                "url": "https://www.youtube.com/watch?v=abcdefghijk",
                "thumbnail": "https://img.youtube.com/vi/abcdefghijk/hqdefault.jpg",
                "provider": "YouTube",
            }
        ][:max_results]

async def test_tts_tur_ayarlarindaki_sesi_ve_hizi_kullanir(container) -> None:
    tts = CapturingTTS()
    container.orchestrator._tts = tts
    events: list[Any] = []

    async def emit(event: Any) -> None:
        events.append(event)

    await container.orchestrator._emit_tts(
        "Merhaba.",
        0,
        ChatOptions(tts=True, tts_voice="tr_TR-dfki-medium", tts_speed=1.2),
        emit,
    )

    assert tts.calls == [{"text": "Merhaba.", "voice": "tr_TR-dfki-medium", "speed": 1.2}]
    assert events[0].type == "tts_chunk"

def test_rag_ve_hafiza_yalnizca_ilgili_soruda_acilir() -> None:
    assert _wants_rag_context("selam") is False
    assert _wants_rag_context("Nasılsın? Ne yapıyorsun?") is False
    assert _wants_rag_context("Chrome'u aç") is False
    assert _wants_rag_context("Bu PDF'te Dijkstra var mı?") is True
    assert _wants_rag_context("Yüklediğim ders notlarında CBS ne diyor?") is True
    assert _wants_memory_context("nasılsın") is False
    assert _wants_memory_context("hava nasıl") is False
    assert _wants_memory_context("HBS klasörünü aç") is False
    assert _wants_memory_context("HBS klasörümü hatırlıyor musun?") is True
    assert _wants_memory_context("Adım neydi?") is True
    assert _select_tool_categories("Nasılsın? Ne yapıyorsun?") is None
    assert "rag" in (_select_tool_categories("Bu PDF'te Dijkstra var mı?") or set())

def test_zayif_rag_otomatik_basilmaz() -> None:
    from app.schemas.chat import SourceRef
    from app.services.chat.orchestrator import (
        _source_refs_from_search_payload,
        _strong_rag_sources,
    )

    weak = SourceRef(chunk_id="a", document_id="d", filename="not.pdf", score=0.2, snippet="x")
    strong = SourceRef(chunk_id="b", document_id="d", filename="not.pdf", score=0.6, snippet="y")
    assert _strong_rag_sources([weak, strong]) == [strong]
    refs = _source_refs_from_search_payload(
        {
            "results": [
                {
                    "filename": "hbs.pdf",
                    "score": 0.8,
                    "content": "CBS",
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "page": 2,
                }
            ]
        }
    )
    assert refs[0].filename == "hbs.pdf"
    assert refs[0].page == 2
    assert refs[0].score == 0.8

def test_basit_sorularda_dusunme_kapatilir() -> None:
    assert _should_skip_thinking("Sen neler yapabilirsin?") is True
    assert _should_skip_thinking("merhaba") is True
    assert _should_skip_thinking("Kimsin") is True
    assert _should_skip_thinking("RTX 5070 için vLLM ayarlarını nasıl optimize ederim?") is False

def test_dusunme_acikken_cevap_icin_ekstra_token_ayrilir() -> None:
    assert _generation_max_tokens(ChatOptions(max_tokens=1024), thinking=False) == 1024
    assert _generation_max_tokens(ChatOptions(max_tokens=1024), thinking=True) == 1792
    assert _generation_max_tokens(ChatOptions(max_tokens=None), thinking=True) == 1792
    assert _generation_max_tokens(ChatOptions(max_tokens=8192), thinking=True) == 4096

def test_tool_semalari_baglam_butcesine_sigdirilir() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": "a" * 600,
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in ("delete_file", "web_search", "run_powershell", "search_memory", "git_push")
    ]

    fitted = _fit_tools_to_context(tools, budget_tokens=500)
    names = [tool["function"]["name"] for tool in fitted]

    assert names == ["web_search", "search_memory"], "en sık kullanılanlar korunur"
    assert _tool_schema_tokens(fitted) <= 500

def test_tool_butcesi_yetiyorse_hicbir_arac_atilmaz() -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": name, "description": "kısa", "parameters": {}},
        }
        for name in ("web_search", "read_file", "delete_file")
    ]

    assert len(_fit_tools_to_context(tools, budget_tokens=2400)) == 3

def test_uzun_gecmis_baglam_penceresine_sigacak_sekilde_kirpilir() -> None:
    system = ChatMessage(role="system", content="Sistem promptu.")
    history = [
        ChatMessage(role="user" if index % 2 == 0 else "assistant", content="x" * 4000)
        for index in range(12)
    ]
    current = ChatMessage(role="user", content="Son sorum bu.")

    trimmed = _trim_messages_for_context(
        [system, *history, current],
        None,
        context_limit=8192,
        output_reserve=1024,
    )

    assert trimmed[0] is system
    assert trimmed[-1] is current
    assert len(trimmed) < len([system, *history, current])
    estimate = sum(_estimate_tokens(message.content) + 8 for message in trimmed)
    assert estimate < 8192 - 1024

def test_kisa_gecmis_kirpilmadan_kalir() -> None:
    messages = [
        ChatMessage(role="system", content="Sistem promptu."),
        ChatMessage(role="user", content="Merhaba"),
        ChatMessage(role="assistant", content="Merhaba, nasıl yardımcı olabilirim?"),
        ChatMessage(role="user", content="Bugün hava nasıl?"),
    ]

    assert (
        _trim_messages_for_context(messages, None, context_limit=8192, output_reserve=1024)
        is messages
    )

async def test_dusunme_tum_tokeni_yiyince_cevap_ikinci_turda_uretilir(container, fake_llm) -> None:
    fake_llm.stream_scripts = [
        [
            StreamDelta(kind="thinking", text="Uzun uzun düşünüyorum..."),
            StreamDelta(kind="finish", finish_reason="length"),
        ],
        [
            StreamDelta(kind="content", text="Dosya arama ve hafıza işlerini yapabilirim."),
            StreamDelta(kind="finish", finish_reason="stop"),
        ],
    ]

    result = await container.orchestrator.run_turn(
        conversation_id=None,
        user_message="Sen neler yapabilirsin?",
        options=ChatOptions(thinking=True, use_tools=False, use_rag=False, use_memory=False),
        emit=_collect_events([]),
    )

    assert result["content"] == "Dosya arama ve hafıza işlerini yapabilirim."
    assert fake_llm.stream_kwargs[0]["enable_thinking"] is False, "yetenek sorusunda THINK kapalı"
    assert fake_llm.stream_kwargs[1]["enable_thinking"] is False, "kurtarma turu düşünmez"

async def test_model_hicbir_sey_uretmezse_kullaniciya_aciklama_donulur(container, fake_llm) -> None:
    fake_llm.stream_scripts = [
        [StreamDelta(kind="finish", finish_reason="length")],
        [StreamDelta(kind="finish", finish_reason="length")],
    ]
    events: list[Any] = []

    result = await container.orchestrator.run_turn(
        conversation_id=None,
        user_message="RTX 5070 için vLLM ayarlarını nasıl optimize ederim?",
        options=ChatOptions(thinking=True, use_tools=False, use_rag=False, use_memory=False),
        emit=_collect_events(events),
    )

    assert "THINK" in result["content"]
    assert any(getattr(event, "type", "") == "token" for event in events)

def _collect_events(events: list[Any]):
    async def emit(event: Any) -> None:
        events.append(event)

    return emit

async def test_windows_tts_piper_kullanmadan_turkce_tolga_olayi_yayar(container) -> None:
    tts = CapturingTTS()
    container.orchestrator._tts = tts
    events: list[Any] = []

    async def emit(event: Any) -> None:
        events.append(event)

    await container.orchestrator._emit_tts(
        "Türkçe cevap.",
        0,
        ChatOptions(
            tts=True,
            tts_voice="windows:Microsoft Tolga - Turkish (Turkey)",
            tts_speed=1.1,
        ),
        emit,
    )

    assert tts.calls == []
    assert events[0].mime_type == "application/x-uryx-windows-tts"
    assert events[0].voice == "Microsoft Tolga - Turkish (Turkey)"
    assert events[0].text == "Türkçe cevap."

async def test_tts_sentence_is_queued_without_waiting_for_synthesis(container) -> None:
    tts = CapturingTTS()
    container.orchestrator._tts = tts
    events: list[Any] = []

    async def emit(event: Any) -> None:
        events.append(event)

    queue: asyncio.Queue[tuple[str, int] | None] = asyncio.Queue(maxsize=8)
    result = await container.orchestrator._handle_delta(
        StreamDelta(kind="content", text="Bu, kuyruğa girecek yeterince uzun bir cümledir. "),
        emit,
        SentenceBuffer(),
        queue,
        0,
        ChatOptions(tts=True),
    )

    assert tts.calls == []
    assert queue.get_nowait()[0].startswith("Bu, kuyruğa")
    assert result["tts_index"] == 1

def test_tts_gorsel_ve_kaynak_url_lerini_okumaz() -> None:
    text = """İşte istediğiniz fotoğraflar:

![Fotoğraf](https://example.com/photo.jpg)
*Kaynak: [Örnek Site](https://example.com/page)*

Dilerseniz başka bir görsel de arayabilirim."""

    spoken = _clean_for_speech(text)

    assert "http" not in spoken
    assert "Fotoğraf" not in spoken
    assert "Kaynak" not in spoken
    assert spoken == "İşte istediğiniz fotoğraflar: Dilerseniz başka bir görsel de arayabilirim."

def test_tts_uzun_listeleri_ve_kod_bloklarini_okumaz() -> None:
    spoken = _clean_for_speech(
        "Sonucu buldum.\n1. Uzun ilk adım.\n- Başka bir madde.\n```python\nprint('x')\n```"
    )
    assert spoken == "Sonucu buldum."

def test_medya_acma_komutunu_islem_olarak_tanir() -> None:
    assert _media_open_requested("Manifest şarkısını sen aç") is True
    assert _media_open_requested("YouTube'dan bir video oynat") is True
    assert _media_open_requested("Manifest şarkısı nedir?") is False
    assert _media_open_requested("manifest sarkisini ac") is True

def test_araclar_acik_niyette_daraltilir_bilinmeyende_korunur() -> None:
    assert _select_tool_categories("internette fotoğrafını bul ve aç") == {
        "web",
        "application",
    }
    assert _select_tool_categories("GPU ve RAM kullanımını göster") == {"system"}
    assert _select_tool_categories("yarın ne yapmalıyım") is None

def test_icerik_getirme_ile_pencere_acma_ayrilir() -> None:
    assert _image_search_requested("Megan Fox son Instagram fotoğraflarını getir") is False
    assert _social_post_requested("Megan Fox son Instagram fotoğraflarını getir") is True
    assert _video_search_requested("YouTube'dan Manifest videosu getir") is True
    assert _browser_open_requested("Spotify uygulamasını aç") is True
    assert _browser_open_requested("Manifest'in son şarkısı ne?") is False
    assert (
        _social_post_requested("Megan Fox'un Instagram'daki son gönderisini bul ve göster") is True
    )
    assert _social_post_requested("Hey Uryx, Megan Fox'un son postunu getirir misin?") is False
    assert _social_post_requested("Megan Fox'un fotosunu getir") is False
    assert _image_search_requested("Megan Fox'un fotosunu getir") is True
    assert _image_search_requested("Megan Fox'un en son fotoğrafı") is True
    assert _image_search_requested("Megan Fox'un fotosunu aç") is True
    assert _fresh_web_lookup_requested("Megan Fox'un en son fotoğrafı") is False
    assert _fresh_web_lookup_requested("Bitcoin güncel fiyatı") is True
    research_hijack = [
        {
            "id": "bad-research",
            "type": "function",
            "function": {"name": "web_research", "arguments": '{"query":"megan fox"}'},
        }
    ]
    guarded_photo = _guard_tool_calls("Megan Fox'un en son fotoğrafı", research_hijack)
    assert guarded_photo[0]["function"]["name"] == "web_image_search"
    assert _liked_spotify_requested("Spotify'da beğeniler listemi çal") is True
    assert (
        _liked_spotify_requested("Spotify'da beğendiklerimin listesindeki son şarkıyı aç") is True
    )
    assert _spotify_library_play_requested("Spotify'daki son şarkıyı aç") is True
    assert _spotify_library_play_requested("Manifest'in son şarkısını aç") is False
    assert _liked_spotify_requested("Manifest'in son şarkısını aç") is False
    assert "megan" in _image_search_subject("Megan Fox'un fotosunu getirir misin?")

def test_spotify_kontrol_komutlari_eyleme_cevrilir() -> None:
    assert _media_control_action("Müziği durdur") == "pause"
    assert _media_control_action("Spotify'ı kapat") == "close"
    assert _media_control_action("Sonraki şarkıya geç") == "next"
    assert _media_control_action("Oynatmaya devam et") == "play"
    assert _media_control_action("Manifest'in en son çıkan şarkısını Spotify'da aç") is None
    assert _latest_media_requested("Manifest'in en son çıkan şarkısını aç") is True

def test_bilgi_istegindeki_tarayıcı_cagrisi_aramaya_cevrilir(container) -> None:
    calls = [
        {
            "id": "bad",
            "type": "function",
            "function": {
                "name": "browser_open",
                "arguments": '{"url":"https://open.spotify.com/track/fake"}',
            },
        }
    ]
    guarded = _guard_tool_calls("Manifest'in son şarkısı ne?", calls)
    assert guarded[0]["function"]["name"] == "web_research"

    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Manifest'in son şarkısı ne?", schemas, {"web"})
    assert {item["function"]["name"] for item in filtered} == {"web_research"}

def test_gorsel_getirme_llm_talimati_yerine_dogrudan_sonuc_verir() -> None:
    executed = [{"tool_name": "web_video_search", "success": True, "result": {"count": 4}}]
    assert _direct_retrieval_response("Manifest videosunu getir", executed) == (
        "4 video buldum; merkez ekranda gösteriyorum."
    )

def test_video_sorgusu_konusunu_konusma_dolgusundan_ayirir() -> None:
    assert _video_search_subject("Youtube'dan Manifest videosu getirir misin?") == "manifest"
    assert _youtube_video_id("https://www.youtube.com/watch?v=vso1LpaQRbo") == "vso1LpaQRbo"

def test_medya_saglayicisinin_resmi_sonucunu_onceliklendirir() -> None:
    results = [
        {"url": "https://example.com/list"},
        {"url": "https://www.youtube.com/watch?v=abcdefghijk"},
    ]

    assert "youtube.com" in _select_media_url("YouTube'da videoyu aç", results)

def test_spotify_arama_sorgusu_oynatilabilir_parcaya_daraltilir() -> None:
    query = _media_search_query("Manifest'in en son çıkan şarkısını aç")
    assert query.startswith("site:open.spotify.com")
    assert "/track" not in query.split()[0]
    assert "manifest" in query
    assert (
        "toz pembe"
        in _media_search_query(
            "Manifest'in en son çıkan şarkısını aç", subject_override="Manifest Toz Pembe"
        ).casefold()
    )

    results = [
        {"url": "https://support.spotify.com/article/search/"},
        {"url": "https://open.spotify.com/track/24CSPGkF9QB1zW07dgtZhr"},
    ]
    assert _select_media_url("Manifest şarkısını aç", results).endswith("24CSPGkF9QB1zW07dgtZhr")
    latest = [
        {"url": "https://open.spotify.com/track/24CSPGkF9QB1zW07dgtZhr"},
        {"url": "https://open.spotify.com/album/3nZq2bNFA4o1zBRlBx2S0K"},
    ]
    assert _select_media_url("Manifest'in en son çıkan şarkısını aç", latest).endswith(
        "3nZq2bNFA4o1zBRlBx2S0K"
    )
    assert (
        _spotify_kind("https://open.spotify.com/album/3nZq2bNFA4o1zBRlBx2S0K", "Manifest son şarkı")
        == "album"
    )
    assert _spotify_kind("", "Spotify'da beğeniler listemi çal") == "liked"

def test_instagram_resmi_profili_ve_en_yeni_gonderiyi_dogrular() -> None:
    evidence = [
        {
            "title": "Megan Fox fan page",
            "summary": "Fan account",
            "url": "https://www.instagram.com/meganfox__daily/",
        },
        {
            "title": "Megan Fox (@meganfox) • Instagram photos and videos",
            "summary": "Official profile",
            "url": "https://www.instagram.com/meganfox/",
        },
        {
            "title": "Megan Fox on Instagram",
            "summary": "Mar 4, 2026 · meganfox on March 4, 2026",
            "url": "https://www.instagram.com/meganfox/reel/DVeUmd_EuAB/",
        },
        {
            "title": "Megan Fox on Instagram",
            "summary": "Jul 16, 2026 · meganfox on July 16, 2026",
            "url": "https://www.instagram.com/p/Da3eqRuksed/",
        },
        {
            "title": "Entertainment Tonight on Instagram about Megan Fox",
            "summary": "Aug 1, 2026 · entertainmenttonight on August 1, 2026: Megan Fox news",
            "url": "https://www.instagram.com/p/NotMeganFoxPost/",
        },
    ]

    result = _resolve_instagram_profile("Megan Fox", evidence)

    assert (
        _social_search_subject("Megan Fox'un Instagram'daki son gönderisini bul ve göster")
        == "Megan Fox"
    )
    assert result["resolved"] is True
    assert result["handle"] == "meganfox"
    assert result["profile_url"] == "https://www.instagram.com/meganfox/"
    assert result["latest_post_url"].endswith("/Da3eqRuksed/")

def test_sosyal_kapsama_guncel_haber_tarihini_ve_gomulu_postu_kullanir() -> None:
    results = [
        {
            "title": "Megan Fox returns with new Instagram photos",
            "summary": "Megan Fox shared an Instagram post.",
            "url": "https://example.com/2026/03/04/old-post/",
        },
        {
            "title": "Megan Fox shares latest Instagram photos",
            "summary": "Megan Fox posted a new Instagram carousel.",
            "url": "https://example.com/current/",
            "published": "2026-07-17T12:00:00+00:00",
        },
    ]

    ranked = _rank_social_coverage(
        results,
        subject="Megan Fox",
        caption="",
        indexed_date="2026-3-4",
    )
    urls = _instagram_post_urls_from_html(
        r'<blockquote data-instgrm-permalink="https:\/\/www.instagram.com\/p\/Da3eqRuksed\/">'
    )

    assert ranked[0]["url"] == "https://example.com/current/"
    assert urls == ["https://www.instagram.com/p/Da3eqRuksed/"]

def test_sosyal_galeri_yalnizca_kaydedilen_gorsellerden_sonra_basari_soyler() -> None:
    executed = [
        {
            "tool_name": "web_social_profile",
            "success": True,
            "result": {
                "resolved": True,
                "handle": "meganfox",
                "latest_post_url": "https://www.instagram.com/p/Da3eqRuksed/",
            },
        },
        {
            "tool_name": "browser_save_images",
            "success": True,
            "result": {
                "count": 6,
                "source": "https://pagesix.com/verified-coverage/",
                "images": [{"path": "C:/Users/Test/Pictures/post.jpg"}],
            },
        },
    ]

    response = _direct_social_response("Megan Fox'un Instagram son postunu göster", executed)

    assert response is not None
    assert "Uryx Web'de bir kez giriş yap" in response
    assert "6 görseli merkezde" not in response

def test_instagram_giris_duvari_arac_sonucundan_taninir() -> None:
    assert _instagram_login_wall({"login_required": True}) is True
    assert (
        _instagram_login_wall({"url": "https://www.instagram.com/accounts/login/?next=/p/abc/"})
        is True
    )
    assert (
        _instagram_login_wall(
            {"url": "https://www.instagram.com/p/abc/", "title": "Login • Instagram"}
        )
        is True
    )
    assert (
        _instagram_login_wall({"url": "https://www.instagram.com/p/abc/", "title": "Megan Fox"})
        is False
    )
    assert _instagram_login_wall(None) is False

def test_instagram_giris_isteyince_gorunur_pencere_acilir_ve_dogru_soylenir() -> None:
    executed = [
        {
            "tool_name": "web_social_profile",
            "success": True,
            "result": {
                "resolved": True,
                "handle": "meganfox",
                "latest_post_url": "https://www.instagram.com/p/Da3eqRuksed/",
            },
        },
        {
            "tool_name": "browser_open",
            "success": True,
            "result": {
                "url": "https://www.instagram.com/accounts/login/?next=/p/Da3eqRuksed/",
                "login_required": True,
                "image_count": 0,
            },
        },
    ]

    response = _direct_social_response("Megan Fox'un Instagram son gönderisini göster", executed)

    assert response is not None
    assert "Uryx Web" in response
    assert "giriş yap" in response

def test_medya_eylemi_yalnizca_dogrulanmis_oynatmayi_basari_sayar() -> None:
    verified = [
        {
            "tool_name": "open_media_application",
            "success": True,
            "result": {"opened": True, "app": "Spotify", "playback_verified": True},
        }
    ]
    unverified = [
        {
            "tool_name": "open_media_application",
            "success": True,
            "result": {"opened": True, "app": "Spotify", "playback_verified": False},
        }
    ]
    assert "oynatmayı başlattım" in (_direct_action_response("şarkıyı aç", verified) or "")
    assert "doğrulayamadım" in (_direct_action_response("şarkıyı aç", unverified) or "")

async def test_arama_sonucundaki_medya_acma_komutu_browser_open_cagirir(container) -> None:
    executed = [
        {
            "tool_name": "web_search",
            "success": True,
            "result": {"results": [{"url": "https://music.youtube.com/watch?v=test"}]},
        }
    ]
    container.orchestrator._run_tool_calls = AsyncMock(return_value=[])

    await container.orchestrator._auto_open_media_result(
        "Manifest şarkısını aç",
        executed,
        conversation_id="conversation",
        emit=AsyncMock(),
        confirm=None,
        confirmation_enabled=True,
    )

    pending_calls = container.orchestrator._run_tool_calls.await_args.args[0]
    assert pending_calls[0]["function"]["name"] == "browser_open"
    assert "music.youtube.com" in pending_calls[0]["function"]["arguments"]

async def test_web_arama_araclari_sonuc_dondurur(container) -> None:
    container.backend_tools._web_search = FakeWebSearch()

    text = await container.backend_tools.execute(
        "web_search", {"query": "güncel haber", "max_results": 3}
    )
    research = await container.backend_tools.execute(
        "web_research", {"query": "güncel haber", "max_results": 5}
    )
    images = await container.backend_tools.execute(
        "web_image_search", {"query": "örnek kişi", "max_results": 4}
    )
    videos = await container.backend_tools.execute(
        "web_video_search", {"query": "örnek video", "max_results": 4}
    )

    assert text["results"][0]["url"] == "https://example.com"
    assert research["source_count"] == 1
    assert images["images"][0]["image"].endswith("image.jpg")
    assert videos["videos"][0]["url"].startswith("https://www.youtube.com/")

def test_orta_risk_onayi_tur_bazinda_kapatilabilir(container) -> None:
    _, _, needs_confirmation = container.executor.inspect(
        "open_application", {"name": "notepad"}, confirmation_enabled=False
    )
    _, _, high_risk_confirmation = container.executor.inspect(
        "delete_file", {"path": "C:/tmp/a.txt"}, confirmation_enabled=False
    )

    assert needs_confirmation is False
    assert high_risk_confirmation is True

def test_web_aramasi_yapilan_tur_hafizaya_yazilmaz() -> None:
    executed = [{"tool_name": "web_search", "success": True}]
    assert _memory_worthy_turn("İSKİ genel müdürü kim şu an?", executed) is False

def test_kullanici_hatirla_derse_web_turu_da_degerlendirilir() -> None:
    executed = [{"tool_name": "web_search", "success": True}]
    assert _memory_worthy_turn("Bunu ara ve hatırla: RTX 5070 fiyatı", executed) is True

def test_kullanici_kendi_bilgisini_verirse_web_turu_degerlendirilir() -> None:
    executed = [{"tool_name": "browser_open", "success": True}]
    assert _memory_worthy_turn("Benim adım Uğur, şu siteyi aç", executed) is True

def test_arac_kullanilmayan_tur_her_zaman_degerlendirilir() -> None:
    assert _memory_worthy_turn("Kod yazarken 4 boşluk girinti kullanıyorum.", []) is True

def test_yerel_arac_turlari_hafizaya_kapatilmaz() -> None:
    executed = [{"tool_name": "get_gpu_usage", "success": True}]
    assert _memory_worthy_turn("Ekran kartım ne kadar yükte?", executed) is True

def test_web_araclari_model_allowlistinde(container) -> None:
    names = {schema["function"]["name"] for schema in container.registry.openai_schemas()}
    assert {
        "web_search",
        "web_research",
        "web_social_profile",
        "web_image_search",
        "web_video_search",
        "web_news",
        "web_fetch",
        "wiki_lookup",
        "fx_rate",
        "weather",
        "public_holidays",
        "air_quality",
        "dict_lookup",
        "earthquakes",
        "country_info",
        "prayer_times",
        "sun_times",
        "postal_lookup",
        "iss_now",
        "space_weather",
        "doi_lookup",
        "elevation",
        "pypi_lookup",
        "ip_lookup",
        "food_barcode",
        "npm_lookup",
        "dns_lookup",
        "pollen",
        "browser_open",
        "browser_read_page",
        "browser_scroll",
        "browser_capture",
        "browser_save_images",
        "control_media_playback",
    } <= names

async def test_hibrit_llm_karmasik_arastirmayi_buluta_yukseltir(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)

    await client.complete(
        [ChatMessage(role="user", content="Bu konuyu kapsamlı araştır ve analiz et")]
    )

    assert cloud.calls
    assert not fake_llm.calls

async def test_yerel_llm_kapaliyken_buluta_gider(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    fake_llm.healthy = False
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)

    await client.complete([ChatMessage(role="user", content="Merhaba")])

    assert cloud.calls
    assert not fake_llm.calls

async def test_iki_saglayici_da_dusunce_hata_ikisini_de_soyler(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    fake_llm.unavailable = True
    cloud.unavailable = True
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)

    with pytest.raises(LLMUnavailableError) as excinfo:
        async for _delta in client.stream([ChatMessage(role="user", content="Merhaba")]):
            pass

    assert "Yerel model" in excinfo.value.user_message
    assert "Bulut model" in excinfo.value.user_message
    assert set(excinfo.value.details) == {"local", "gemini"}

async def test_hibrit_llm_ozel_belge_baglamini_yerelde_tutar(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)
    messages = [
        ChatMessage(role="system", content="Sistem\nBELGELERDEN İLGİLİ BÖLÜMLER\nözel içerik"),
        ChatMessage(role="user", content="Bunu kapsamlı analiz et"),
    ]

    await client.complete(messages)

    assert fake_llm.calls
    assert not cloud.calls

async def test_hibrit_llm_read_file_arac_sonucunu_yerelde_tutar(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)
    messages = [
        ChatMessage(role="user", content="Bunu kapsamlı analiz et ve kaynakları tara"),
        ChatMessage(role="tool", name="read_file", content="özel not içeriği"),
    ]

    await client.complete(messages)

    assert fake_llm.calls
    assert not cloud.calls

async def test_hibrit_llm_read_text_file_adina_guvenmez(settings, fake_llm) -> None:
    cloud = type(fake_llm)()
    hybrid_settings = settings.model_copy(
        update={"gemini_enabled": True, "gemini_api_key": "test", "llm_routing_mode": "hybrid"}
    )
    client = HybridLLMClient(hybrid_settings, local=fake_llm, cloud=cloud)
    messages = [
        ChatMessage(role="user", content="Bunu kapsamlı analiz et"),
        ChatMessage(role="tool", name="read_text_file", content="sahte"),
    ]

    await client.complete(messages)

    assert cloud.calls
    assert not fake_llm.calls
