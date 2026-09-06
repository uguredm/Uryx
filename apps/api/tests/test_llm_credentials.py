"""Gemini kimlik bilgisi uçları — maskeleme, kayıt, silme, yetki."""

from __future__ import annotations

import json

import pytest
from app.core.container import Container
from app.services.llm.credentials import hint_for
from app.services.llm.hybrid_client import HybridLLMClient

TEST_KEY = "ui-test-key-9f3a"

def _blank_runtime_gemini(container: Container) -> None:
    """Geliştirici ``.env`` anahtarının test cevaplarına karışmasını engeller."""
    settings = container.settings
    object.__setattr__(settings, "gemini_api_key", "")
    object.__setattr__(settings, "gemini_enabled", False)
    container.env_gemini_api_key = ""
    container.env_gemini_enabled = False

def test_hint_son_dort_karakter() -> None:
    assert hint_for("") == ""
    assert hint_for("ab") == "ab"
    assert hint_for(TEST_KEY) == "9f3a"

async def test_configure_cloud_istemciyi_degistirir(settings, fake_llm) -> None:
    hybrid = HybridLLMClient(settings, local=fake_llm, cloud=None)
    cloud = type(fake_llm)()
    await hybrid.configure_cloud(cloud)
    assert hybrid.cloud_configured is True
    await hybrid.configure_cloud(None)
    assert hybrid.cloud_configured is False

class TestLlmCredentialsApi:
    """REST uçları."""

    @pytest.fixture(autouse=True)
    def _blank_gemini(self, container: Container) -> None:
        _blank_runtime_gemini(container)

    async def test_maskeli_get_anahtari_sizdirmaz(self, client) -> None:
        put = await client.put(
            "/api/v1/system/llm-credentials",
            json={"api_key": TEST_KEY, "model": "gemini-3-flash-preview"},
        )
        assert put.status_code == 200
        body = put.json()
        raw = json.dumps(body)
        assert TEST_KEY not in raw
        assert "api_key" not in body
        assert body["configured"] is True
        assert body["hint"] == "9f3a"
        assert body["source"] == "ui"
        assert body["provider"] == "gemini"
        assert body["provider_label"] == "Google Gemini"

        listed = await client.get("/api/v1/settings")
        listed_raw = json.dumps(listed.json())
        assert listed.status_code == 200
        assert "llm_credentials" not in listed.json()
        assert TEST_KEY not in listed_raw

        hidden = await client.get("/api/v1/settings/llm_credentials")
        assert hidden.status_code == 404

    async def test_put_sonrasi_cloud_configured(self, client) -> None:
        before = await client.get("/api/v1/system/config")
        assert before.json()["llm"]["cloud_configured"] is False

        saved = await client.put(
            "/api/v1/system/llm-credentials",
            json={"api_key": TEST_KEY},
        )
        assert saved.status_code == 200

        after = await client.get("/api/v1/system/config")
        payload = after.json()
        assert payload["llm"]["cloud_configured"] is True
        assert TEST_KEY not in json.dumps(payload)

        revealed = await client.get("/api/v1/system/llm-credentials/reveal")
        assert revealed.status_code == 200
        assert revealed.json()["api_key"] == TEST_KEY
        assert revealed.json()["source"] == "ui"

    async def test_openai_anahtari_saglayiciyi_algilar(self, client) -> None:
        saved = await client.put(
            "/api/v1/system/llm-credentials",
            json={"api_key": "sk-proj-uryxtestkey1234"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["provider"] == "openai"
        assert body["provider_label"] == "OpenAI"
        assert body["model"] == "gpt-4o-mini"
        assert "sk-proj" not in json.dumps(body)

        config = await client.get("/api/v1/system/config")
        assert config.json()["llm"]["cloud_provider"] == "openai"
        assert config.json()["llm"]["cloud_model"] == "gpt-4o-mini"

    async def test_anthropic_anahtari_reddedilir(self, client) -> None:
        denied = await client.put(
            "/api/v1/system/llm-credentials",
            json={"api_key": "sk-ant-api03-abc"},
        )
        assert denied.status_code == 422
        assert "OpenRouter" in denied.json()["error"]["message"]

    async def test_bos_anahtar_siler(self, client) -> None:
        await client.put("/api/v1/system/llm-credentials", json={"api_key": TEST_KEY})
        cleared = await client.put("/api/v1/system/llm-credentials", json={"api_key": ""})
        assert cleared.status_code == 200
        body = cleared.json()
        assert body["source"] != "ui"
        assert TEST_KEY not in json.dumps(body)

        config = await client.get("/api/v1/system/config")
        assert config.json()["llm"]["cloud_configured"] is False

        deleted = await client.put(
            "/api/v1/system/llm-credentials", json={"api_key": TEST_KEY}
        )
        assert deleted.status_code == 200
        gone = await client.delete("/api/v1/system/llm-credentials")
        assert gone.status_code == 200
        assert gone.json()["source"] != "ui"

    async def test_reveal_tokensiz_401(self, app) -> None:
        import httpx
        from app.core.config import get_settings

        settings = get_settings()
        original = settings.uryx_local_token
        object.__setattr__(settings, "uryx_local_token", "test-token")
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                denied = await http.get("/api/v1/system/llm-credentials/reveal")
                assert denied.status_code == 401
                allowed = await http.get(
                    "/api/v1/system/llm-credentials/reveal",
                    headers={"X-Uryx-Token": "test-token"},
                )
                assert allowed.status_code == 200
                assert "api_key" in allowed.json()
        finally:
            object.__setattr__(settings, "uryx_local_token", original)
