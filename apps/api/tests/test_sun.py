"""sun_times — Open-Meteo sunrise/UV, weather rewrite yok, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _sun_times_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.sun import lookup_sun_times, sun_times_url

def test_url_alias() -> None:
    url = sun_times_url(41.01, 28.97, days=1)
    assert "api.open-meteo.com" in url
    assert "sunrise" in url
    assert "uv_index_max" in url
    tool = ToolRegistry().get("sun_times")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "sun_times" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("sunrise") == "sun_times"
    assert normalize_tool_name("uv") == "sun_times"
    assert "sun_times" in BASE_SYSTEM_PROMPT
    assert _sun_times_requested("İstanbul gün batımı") is True
    assert _sun_times_requested("İstanbul namaz vakitleri") is False
    assert _sun_times_requested("İstanbul hava durumu") is False

def test_intent_filtre_gunes(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Ankara gün doğumu ve UV", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "sun_times" in names
    assert "weather" not in names
    assert "prayer_times" not in names

async def test_liste_ve_yonlendirme() -> None:
    class Geo:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "name": "Ankara",
                        "country": "Türkiye",
                        "latitude": 39.9,
                        "longitude": 32.8,
                    }
                ]
            }

        def raise_for_status(self) -> None:
            return None

    class Sun:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "daily": {
                    "time": ["2026-08-16"],
                    "sunrise": ["2026-08-16T06:05"],
                    "sunset": ["2026-08-16T19:50"],
                    "uv_index_max": [8.2],
                }
            }

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            self.n = 0

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Geo | Sun:
            self.n += 1
            if "geocoding" in url:
                return Geo()
            assert "api.open-meteo.com" in url
            return Sun()

    with patch("app.services.web.sun.httpx.AsyncClient", Client):
        out = await lookup_sun_times("Ankara")
    assert out["sunrise"].startswith("2026-08-16")
    assert out["uv_label"] == "çok yüksek"

async def test_yonlendirme_red() -> None:
    class Redirect:
        status_code = 302
        headers: ClassVar[dict[str, str]] = {"location": "https://evil.example/"}

        def json(self) -> dict[str, str]:
            return {}

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Redirect:
            return Redirect()

    with (
        patch("app.services.web.sun.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_sun_times("İzmir")
