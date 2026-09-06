"""Ses aktarımı ve göreli tarih bağlamı regresyon testleri."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from app.services.llm.prompts import _istanbul_timezone, _turkish_date, build_system_prompt
from app.services.stt.client import WhisperClient, sanitize_transcription
from app.services.stt.quality import (
    DEFAULT_HOTWORDS,
    is_backchannel,
    is_low_quality_segment,
    whisper_decode_hints,
)
from app.services.stt.stream import (
    AudioStreamBuffer,
    parse_stream_config,
    parse_stream_event,
    should_emit_partial,
    stream_control,
)
from app.services.tts.client import SentenceBuffer
from app.services.web.search import WebSearchService

def test_system_prompt_contains_exact_istanbul_relative_dates() -> None:
    """Model dün/b bugün/yarın hesabını kendi tahmin etmemeli."""
    now = datetime.now(_istanbul_timezone())
    prompt = build_system_prompt()

    assert "GÜNCEL ZAMAN (Europe/Istanbul)" in prompt
    assert f"Bugün: {_turkish_date(now)}" in prompt
    assert f"Dün: {_turkish_date(now - timedelta(days=1))}" in prompt
    assert f"Yarın: {_turkish_date(now + timedelta(days=1))}" in prompt
    assert "Instagram latest post" in prompt
    assert "öznesiz sorgu gönderme" in prompt

@pytest.mark.asyncio
async def test_whisper_client_disables_second_vad_by_default(settings) -> None:
    """Masaüstünde bitirilmiş mikrofon kaydı Whisper tarafından tekrar budanmamalı."""
    captured_body = b""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = await request.aread()
        return httpx.Response(
            200,
            json={
                "text": "Hey Uryx",
                "language": "tr",
                "duration": 1.2,
                "segments": [],
                "model": "medium",
                "device": "cuda",
            },
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://whisper.test",
    )
    client = WhisperClient(settings, client=http_client)
    try:
        result = await client.transcribe(b"audio", "recording.webm", language="tr")
    finally:
        await http_client.aclose()

    assert result.text == "Hey Uryx"
    assert b'name="vad_filter"' in captured_body
    assert b"false" in captured_body
    assert b'name="hotwords"' in captured_body
    assert b"Uryx" in captured_body

@pytest.mark.asyncio
async def test_whisper_client_drops_noise_and_backchannel(settings) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text": "hmm Spotify'ı aç gürültü",
                "language": "tr",
                "duration": 2.0,
                "segments": [
                    {"start": 0.0, "end": 0.3, "text": "hmm", "no_speech_prob": 0.1},
                    {
                        "start": 0.3,
                        "end": 1.2,
                        "text": "Spotify'ı aç",
                        "no_speech_prob": 0.1,
                        "avg_logprob": -0.2,
                    },
                    {"start": 1.2, "end": 1.6, "text": "gürültü", "no_speech_prob": 0.95},
                ],
                "model": "medium",
                "device": "cuda",
            },
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://whisper.test",
    )
    client = WhisperClient(settings, client=http_client)
    try:
        result = await client.transcribe(b"audio", "recording.webm", language="tr")
    finally:
        await http_client.aclose()

    assert result.text == "Spotify'ı aç"
    assert len(result.segments) == 1

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ayakta mısın? Altyazı M.K.", ""),
        (
            "Türkçe konuşma kaydı. Noktalama işaretlerini ve büyük harfleri doğru kullan.",
            "",
        ),
        (
            "Türkçe konuşma kaydı. Noktalama işaretlerini ve büyük harflerini doğru kullan.",
            "",
        ),
        ("Yarın toplantı var. Altyazı M.K.", "Yarın toplantı var."),
        ("İzlediğiniz için teşekkür ederim.", ""),
        ("Spotify'ı aç", "Spotify'ı aç"),
    ],
)
def test_whisper_hallucinations_are_filtered(raw: str, expected: str) -> None:
    assert sanitize_transcription(raw) == expected

def test_whisper_low_quality_segments_are_dropped() -> None:
    assert is_low_quality_segment(no_speech_prob=0.92) is True
    assert is_low_quality_segment(avg_logprob=-1.8) is True
    assert is_low_quality_segment(compression_ratio=3.1) is True
    assert (
        is_low_quality_segment(
            no_speech_prob=0.1, avg_logprob=-0.3, compression_ratio=1.2
        )
        is False
    )
    assert (
        is_low_quality_segment(no_speech_prob=0.92, avg_logprob=-0.2) is False
    )
    assert is_backchannel("hmm") is True
    assert is_backchannel("Spotify'ı aç") is False

def test_faster_whisper_hotwords_prefix_yokken_gider() -> None:
    hints = whisper_decode_hints()
    assert hints == {"hotwords": DEFAULT_HOTWORDS}
    assert "Uryx" in hints["hotwords"]
    assert "prefix" not in hints
    assert whisper_decode_hints(prefix="  not ") == {"prefix": "not"}
    start = stream_control("start", language="tr")
    assert start["hotwords"] == DEFAULT_HOTWORDS
    assert start["type"] == "start"
    assert parse_stream_config({"type": "end", "language": "tr"}) == (
        "tr",
        DEFAULT_HOTWORDS,
    )
    assert parse_stream_config({"prefix": "x", "hotwords": "Uryx"}) == ("", "")

def test_whisper_stream_buffer_partial_then_flush() -> None:
    buffer = AudioStreamBuffer(partial_bytes=8, max_bytes=64)
    assert buffer.feed(b"1234") is False
    assert buffer.feed(b"5678") is True
    assert buffer.snapshot() == b"12345678"
    buffer.mark_partial()
    assert buffer.flush() == b"12345678"
    assert len(buffer) == 0
    assert parse_stream_event({"type": "final", "text": " aç "}) == ("final", "aç")
    assert should_emit_partial("", "") is False
    assert should_emit_partial("", "hmm") is False
    assert should_emit_partial("Spotify'ı aç", "Spotify'ı aç") is False
    assert should_emit_partial("", "Spotify'ı aç") is True

def test_tts_ilk_cumle_hemen_flush_olur() -> None:
    buffer = SentenceBuffer(min_chars=25, first_min_chars=6)
    ready = buffer.feed("Anladım. Şimdi Spotify'ı açıyorum hemen. ")
    assert ready[0] == "Anladım."
    assert any("Spotify" in piece for piece in ready)

@pytest.mark.asyncio
async def test_instagram_image_search_rejects_unrelated_sources(monkeypatch) -> None:
    """Genel haber görseli Instagram son postu olarak sunulmamalı."""

    class FakeDDGS:
        def __init__(self, **_kwargs) -> None:
            pass

        def images(self, *_args, **_kwargs) -> list[dict[str, object]]:
            return [
                {
                    "title": "Genel Instagram haberi",
                    "image": "https://news.example/general.jpg",
                    "url": "https://news.example/instagram-features",
                },
                {
                    "title": "Doğrulanmış profil gönderisi",
                    "image": "https://cdn.example/post.jpg",
                    "url": "https://www.instagram.com/example/p/ABC123/",
                },
            ]

    monkeypatch.setitem(__import__("sys").modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    images = await WebSearchService().image_search(
        "Example Person Instagram latest post", max_results=6
    )

    assert len(images) == 1
    assert images[0]["source"] == "https://www.instagram.com/example/p/ABC123/"

@pytest.mark.asyncio
async def test_whisper_client_reload_posts_model(settings) -> None:
    """Ayarlardan model değişince Whisper POST /reload alır; konteyner yeniden yaratılmaz."""
    captured: list[httpx.Request] = []
    bodies: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        bodies.append(await request.aread())
        return httpx.Response(
            200,
            json={
                "model_loaded": True,
                "loading": False,
                "model": "small",
                "device": "cpu",
                "language": "tr",
            },
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://whisper.test",
    )
    client = WhisperClient(settings, client=http_client)
    try:
        result = await client.reload("small")
    finally:
        await http_client.aclose()

    assert result.model == "small"
    assert result.available is True
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/reload"
    assert b"small" in bodies[0]

