"""REST API ve WebSocket entegrasyon testleri."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

class TestHealth:
    """Sağlık ve kök endpoint'leri."""

    async def test_health_token_gerektirmez(self, client) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"ok", "degraded"}
        assert "services" in body
        assert body["host_bridge"] in {"up", "down", "degraded"}

    async def test_root_bilgi_dondurur(self, client) -> None:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json()["docs"] == "/docs"

    async def test_openapi_uretilir(self, client) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Uryx API"

        for path in (
            "/api/v1/chat",
            "/api/v1/memory",
            "/api/v1/documents",
            "/api/v1/tools",
            "/api/v1/system/status",
            "/api/v1/system/llm-credentials",
            "/api/v1/speech/stt/reload",
        ):
            assert path in schema["paths"], path

class TestConversations:
    """Sohbet CRUD."""

    async def test_bos_liste(self, client) -> None:
        response = await client.get("/api/v1/chat/conversations")
        assert response.status_code == 200
        assert response.json() == []

    async def test_olustur_getir_sil(self, client) -> None:
        created = await client.post("/api/v1/chat/conversations", json={"title": "Test sohbeti"})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        detail = await client.get(f"/api/v1/chat/conversations/{conversation_id}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Test sohbeti"

        renamed = await client.patch(
            f"/api/v1/chat/conversations/{conversation_id}", json={"title": "Yeni ad"}
        )
        assert renamed.status_code == 200

        deleted = await client.delete(f"/api/v1/chat/conversations/{conversation_id}")
        assert deleted.status_code == 200

        missing = await client.get(f"/api/v1/chat/conversations/{conversation_id}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"

class TestMemoryApi:
    """Hafıza endpoint'leri."""

    async def test_crud_akisi(self, client) -> None:
        created = await client.post(
            "/api/v1/memory",
            json={"content": "Kullanıcı koyu tema tercih ediyor.", "category": "preference"},
        )
        assert created.status_code == 201
        memory_id = created.json()["id"]

        listed = await client.get("/api/v1/memory")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = await client.patch(
            f"/api/v1/memory/{memory_id}",
            json={"content": "Kullanıcı koyu tema ve büyük yazı tipi tercih ediyor."},
        )
        assert updated.status_code == 200
        assert "büyük yazı" in updated.json()["content"]

        pinned = await client.post(f"/api/v1/memory/{memory_id}/pin?pinned=true")
        assert pinned.status_code == 200

        stats = await client.get("/api/v1/memory/stats")
        assert stats.json()["total"] == 1
        assert stats.json()["pinned"] == 1

        removed = await client.delete(f"/api/v1/memory/{memory_id}")
        assert removed.status_code == 200

    async def test_gecersiz_icerik_reddedilir(self, client) -> None:
        response = await client.post("/api/v1/memory", json={"content": "ab"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

class TestToolsApi:
    """Araç endpoint'leri."""

    async def test_arac_listesi(self, client) -> None:
        response = await client.get("/api/v1/tools")
        assert response.status_code == 200
        body = response.json()
        assert len(body["tools"]) > 15
        assert body["host_bridge_connected"] is False

    async def test_onaysiz_riskli_arac_428(self, client) -> None:
        response = await client.post(
            "/api/v1/tools/execute",
            json={"tool_name": "delete_file", "arguments": {"path": "C:/a.txt"}},
        )
        assert response.status_code == 428
        assert response.json()["error"]["code"] == "confirmation_required"

    async def test_confirmed_true_biletsiz_high_428(self, client) -> None:
        response = await client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "delete_file",
                "arguments": {"path": "C:/a.txt"},
                "confirmed": True,
            },
        )
        assert response.status_code == 428

    async def test_prepare_bileti_ile_high_calisir(self, client) -> None:
        prepared = await client.post(
            "/api/v1/tools/prepare",
            json={"tool_name": "delete_file", "arguments": {"path": "C:/a.txt"}},
        )
        assert prepared.status_code == 200
        body = prepared.json()
        assert body["needs_confirmation"] is True
        assert body["confirmation_ticket"]
        executed = await client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "delete_file",
                "arguments": {"path": "C:/a.txt"},
                "confirmation_ticket": body["confirmation_ticket"],
            },
        )
        assert executed.status_code == 200
        assert executed.json()["success"] is False
        assert "masaüstü" in (executed.json()["error"] or "").lower()

    async def test_bilet_tek_kullanimlik(self, client) -> None:
        prepared = await client.post(
            "/api/v1/tools/prepare",
            json={"tool_name": "delete_file", "arguments": {"path": "C:/a.txt"}},
        )
        ticket = prepared.json()["confirmation_ticket"]
        first = await client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "delete_file",
                "arguments": {"path": "C:/a.txt"},
                "confirmation_ticket": ticket,
            },
        )
        assert first.status_code == 200
        replay = await client.post(
            "/api/v1/tools/execute",
            json={
                "tool_name": "delete_file",
                "arguments": {"path": "C:/a.txt"},
                "confirmation_ticket": ticket,
            },
        )
        assert replay.status_code == 428

    async def test_izin_listesi_disi_arac_403(self, client) -> None:
        response = await client.post(
            "/api/v1/tools/execute", json={"tool_name": "format_disk", "arguments": {}}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "tool_not_allowed"

    async def test_eksik_parametre_422(self, client) -> None:
        response = await client.post(
            "/api/v1/tools/execute", json={"tool_name": "open_folder", "arguments": {}}
        )
        assert response.status_code == 422

    async def test_kapatilan_arac_tekrar_acilabilir(self, client) -> None:
        """Devre dışı bırakılan bir araç yeniden etkinleştirilebilmeli."""
        name = "docker_start_container"

        off = await client.post(f"/api/v1/tools/{name}/enabled?enabled=false")
        assert off.status_code == 200

        tools = {t["name"]: t for t in (await client.get("/api/v1/tools")).json()["tools"]}
        assert tools[name]["enabled"] is False

        on = await client.post(f"/api/v1/tools/{name}/enabled?enabled=true")
        assert on.status_code == 200

        tools = {t["name"]: t for t in (await client.get("/api/v1/tools")).json()["tools"]}
        assert tools[name]["enabled"] is True

    async def test_bilinmeyen_arac_acilamaz(self, client) -> None:
        response = await client.post("/api/v1/tools/format_disk/enabled?enabled=true")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "tool_not_allowed"

class TestDocumentsApi:
    """Belge endpoint'leri."""

    async def test_bos_liste_ve_istatistik(self, client) -> None:
        assert (await client.get("/api/v1/documents")).json() == []
        stats = await client.get("/api/v1/documents/stats")
        assert stats.status_code == 200
        assert stats.json()["total"] == 0

    async def test_desteklenen_turler(self, client) -> None:
        response = await client.get("/api/v1/documents/supported")
        extensions = response.json()["extensions"]
        assert ".pdf" in extensions
        assert ".py" in extensions

    async def test_izinsiz_yol_403(self, client) -> None:
        response = await client.post(
            "/api/v1/documents/ingest-path",
            json={"path": "C:/Windows/System32", "recursive": False, "collection": "documents"},
        )
        assert response.status_code == 403

class TestSystemApi:
    """Sistem endpoint'leri."""

    async def test_durum(self, client) -> None:
        response = await client.get("/api/v1/system/status")
        assert response.status_code == 200
        body = response.json()
        assert "services" in body
        assert "metrics" in body
        assert body["host_bridge_connected"] is False

    async def test_config_hassas_veri_sizdirmaz(self, client) -> None:
        response = await client.get("/api/v1/system/config")
        assert response.status_code == 200
        raw = json.dumps(response.json())
        assert "uryx_local_token" not in raw.lower()
        assert "postgres_password" not in raw.lower()

    async def test_config_wake_word_masaüstü_store(self, client) -> None:
        response = await client.get("/api/v1/system/config")
        assert response.status_code == 200
        wake = response.json()["wake_word"]
        assert wake["source"] == "desktop_store"
        assert wake["api_controls"] is False
        assert "enabled" not in wake
        assert "word" not in wake

    async def test_wake_word_sunucu_ayarına_yazılmaz(self, client) -> None:
        response = await client.put("/api/v1/settings/wake_word", json={"enabled": True})
        assert response.status_code == 422

class TestChatFlow:
    """Sohbet akışı (sahte LLM ile)."""

    async def test_rest_sohbet(self, client, fake_llm) -> None:
        fake_llm.reply = "Türkçe test cevabı."
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Merhaba, nasılsın?", "options": {"use_tools": False}},
        )
        assert response.status_code == 200
        body = response.json()
        assert "Türkçe test cevabı" in body["content"]
        assert body["conversation_id"]

    async def test_sohbet_gecmise_kaydedilir(self, client, fake_llm) -> None:
        fake_llm.reply = "Kayıt testi."
        chat = await client.post(
            "/api/v1/chat", json={"message": "Bunu kaydet lütfen", "options": {"use_tools": False}}
        )
        conversation_id = chat.json()["conversation_id"]

        messages = await client.get(f"/api/v1/chat/conversations/{conversation_id}/messages")
        roles = [m["role"] for m in messages.json()]
        assert roles == ["user", "assistant"]

    async def test_bos_mesaj_reddedilir(self, client) -> None:
        response = await client.post("/api/v1/chat", json={"message": ""})
        assert response.status_code == 422

    async def test_vllm_kapaliyken_anlasilir_hata(self, client, fake_llm) -> None:
        """LLM kapalıyken REST sessizce boş cevap dönmemeli."""
        fake_llm.unavailable = True
        response = await client.post(
            "/api/v1/chat", json={"message": "Merhaba", "options": {"use_tools": False}}
        )
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "llm_unavailable"
        assert "LLM" in body["error"]["message"]

    def test_vllm_kapaliyken_ws_error_olayi(self, app, fake_llm) -> None:
        """WebSocket tarafında da açıklayıcı bir `error` olayı yayınlanmalı."""
        fake_llm.unavailable = True

        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json(
                {
                    "type": "user_message",
                    "content": "Merhaba",
                    "options": {"use_tools": False, "use_rag": False, "use_memory": False},
                }
            )

            events = []
            for _ in range(10):
                event = socket.receive_json()
                events.append(event)
                if event["type"] in {"error", "done"}:
                    break

        errors = [e for e in events if e["type"] == "error"]
        assert errors, "LLM kapalıyken error olayı bekleniyor"
        assert errors[0]["code"] == "llm_unavailable"

class TestWebSocketChat:
    """`/ws/chat` protokolü."""

    def test_streaming_akis(self, app, fake_llm) -> None:
        fake_llm.reply = "Bir iki üç"

        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json(
                {
                    "type": "user_message",
                    "content": "Sayıları say",
                    "options": {"use_tools": False, "use_rag": False, "use_memory": False},
                }
            )

            events: list[dict] = []
            for _ in range(30):
                event = socket.receive_json()
                events.append(event)
                if event["type"] in {"done", "error"}:
                    break

        types = [event["type"] for event in events]
        assert types[0] == "start"
        assert "token" in types
        assert types[-1] == "done"

        content = "".join(e["content"] for e in events if e["type"] == "token")
        assert "Bir iki üç" in content

    def test_bos_mesaj_hata_dondurur(self, app) -> None:
        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json({"type": "user_message", "content": "   "})
            event = socket.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "validation_error"

    def test_ping_pong(self, app) -> None:
        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json({"type": "ping"})
            assert socket.receive_json()["type"] == "pong"

    def test_bilinmeyen_olay(self, app) -> None:
        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json({"type": "kim_bu"})
            event = socket.receive_json()
            assert event["type"] == "error"
            assert event["code"] == "unknown_event"

    def test_riskli_arac_onay_ister_ve_red_edilebilir(self, app, fake_llm) -> None:
        fake_llm.tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "arguments": json.dumps({"path": "C:/Users/test/Desktop/a.txt"}),
                },
            }
        ]
        fake_llm.reply = "İşlem iptal edildi."

        with TestClient(app) as test_client, test_client.websocket_connect("/ws/chat") as socket:
            socket.send_json(
                {
                    "type": "user_message",
                    "content": "a.txt dosyasını sil",
                    "options": {"use_rag": False, "use_memory": False},
                }
            )

            confirm_request = None
            for _ in range(20):
                event = socket.receive_json()
                if event["type"] == "tool_confirm_request":
                    confirm_request = event
                    break
                if event["type"] in {"done", "error"}:
                    break

            assert confirm_request is not None, "Riskli araç onay istemeli"
            assert confirm_request["risk_level"] == "high"
            assert confirm_request["tool_name"] == "delete_file"

            socket.send_json(
                {
                    "type": "tool_confirm_response",
                    "request_id": confirm_request["request_id"],
                    "approved": False,
                }
            )

            results = []
            for _ in range(30):
                event = socket.receive_json()
                results.append(event)
                if event["type"] == "done":
                    break

            tool_results = [e for e in results if e["type"] == "tool_result"]
            assert tool_results, "Red sonrası tool_result gelmeli"
            assert tool_results[0]["success"] is False

@pytest.mark.parametrize(
    "path",
    ["/api/v1/memory", "/api/v1/documents", "/api/v1/tools", "/api/v1/system/status"],
)
async def test_token_zorunluyken_401(app, path: str) -> None:
    """Token tanımlıyken korumalı endpoint'ler 401 döner."""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.uryx_local_token
    object.__setattr__(settings, "uryx_local_token", "test-token")
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get(path)).status_code == 401
            ok = await client.get(path, headers={"X-Uryx-Token": "test-token"})
            assert ok.status_code == 200
    finally:
            object.__setattr__(settings, "uryx_local_token", original)

class TestSpeechReload:
    """Whisper modeli canlı reload (Faz 4.3)."""

    async def test_stt_reload_model_degistirir(self, client, container) -> None:
        response = await client.post("/api/v1/speech/stt/reload", json={"model": "small"})
        assert response.status_code == 200
        body = response.json()
        assert body["model"] == "small"
        assert getattr(container.stt, "last_reload", None) == "small"

