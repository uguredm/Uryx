"""air_quality — Open-Meteo AQI, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _air_quality_requested, _filter_tool_schemas
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.air_quality import _eaqi_label, air_quality_url, lookup_air_quality

def test_etiket_url_alias() -> None:
    assert _eaqi_label(12) == "iyi"
    assert _eaqi_label(90) == "çok zayıf"
    assert "air-quality-api.open-meteo.com" in air_quality_url(41.01, 28.97)
    tool = ToolRegistry().get("air_quality")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "air_quality" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("hava_kalitesi") == "air_quality"
    assert normalize_tool_name("aqi") == "air_quality"
    assert "air_quality" in BASE_SYSTEM_PROMPT
    assert _air_quality_requested("İstanbul hava kalitesi") is True
    assert _air_quality_requested("İstanbul hava durumu") is False

def test_intent_filtre_aqi(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Ankara PM2.5 hava kirliliği", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "air_quality" in names
    assert "weather" not in names

async def test_geocode_ve_aqi() -> None:
    class Response:
        def __init__(self, payload: Any) -> None:
            self.status_code = 200
            self.headers: ClassVar[dict[str, str]] = {}
            self._payload = payload

        def json(self) -> Any:
            return self._payload

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Response:
            if "geocoding-api.open-meteo.com" in url:
                return Response(
                    {
                        "results": [
                            {
                                "name": "Ankara",
                                "country": "Türkiye",
                                "latitude": 39.93,
                                "longitude": 32.85,
                            }
                        ]
                    }
                )
            if "air-quality-api.open-meteo.com" in url:
                return Response(
                    {
                        "current": {
                            "time": "2026-08-16T12:00",
                            "european_aqi": 18,
                            "pm10": 12.0,
                            "pm2_5": 8.0,
                            "nitrogen_dioxide": 10.0,
                            "ozone": 40.0,
                        }
                    }
                )
            raise AssertionError(url)

    with patch("app.services.web.air_quality.httpx.AsyncClient", Client):
        out = await lookup_air_quality("ankara")
    assert out["quality"] == "iyi"
    assert out["european_aqi"] == 18

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
        patch("app.services.web.air_quality.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_air_quality("İzmir")
