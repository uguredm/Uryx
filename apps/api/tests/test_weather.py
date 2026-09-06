"""weather — Open-Meteo, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _weather_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.weather import (
    forecast_url,
    geocode_url,
    lookup_weather,
    parse_daily_forecast,
)

def test_url_ve_kayit() -> None:
    tool = ToolRegistry().get("weather")
    assert "geocoding-api.open-meteo.com" in geocode_url("İstanbul")
    assert "forecast_days=3" in forecast_url(41.01, 28.97)
    assert "daily=" in forecast_url(41.01, 28.97, days=5)
    assert "days" in {param.name for param in tool.parameters}
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "weather" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("hava_durumu") == "weather"
    assert normalize_tool_name("get_weather") == "weather"
    assert "weather" in BASE_SYSTEM_PROMPT
    assert _weather_requested("İstanbul'da hava nasıl") is True
    assert _weather_requested("100 dolar kaç TL") is False

def test_intent_filtre_hava(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Ankara hava durumu", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "weather" in names
    assert "web_research" not in names

async def test_geocode_ve_tahmin() -> None:
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
                                "name": "İstanbul",
                                "country": "Türkiye",
                                "latitude": 41.01,
                                "longitude": 28.97,
                            }
                        ]
                    }
                )
            if "api.open-meteo.com" in url:
                return Response(
                    {
                        "current": {
                            "time": "2026-08-16T12:00",
                            "temperature_2m": 28.4,
                            "apparent_temperature": 29.1,
                            "relative_humidity_2m": 55,
                            "weather_code": 0,
                            "wind_speed_10m": 12.0,
                            "precipitation": 0,
                        },
                        "daily": {
                            "time": ["2026-08-16", "2026-08-17"],
                            "weather_code": [0, 61],
                            "temperature_2m_max": [30.0, 27.0],
                            "temperature_2m_min": [22.0, 20.0],
                            "precipitation_sum": [0, 4.2],
                        },
                    }
                )
            raise AssertionError(url)

    with patch("app.services.web.weather.httpx.AsyncClient", Client):
        out = await lookup_weather("istanbul", days=2)
    assert out["temperature_c"] == 28.4
    assert out["condition"] == "açık"
    assert out["place"] == "İstanbul"
    assert len(out["daily"]) == 2
    assert out["daily"][1]["condition"] == "hafif yağmur"

def test_gunluk_satir_ayristir() -> None:
    rows = parse_daily_forecast(
        {
            "daily": {
                "time": ["2026-08-16"],
                "weather_code": [3],
                "temperature_2m_max": [24],
                "temperature_2m_min": [18],
                "precipitation_sum": [1.5],
            }
        }
    )
    assert rows[0]["tmax_c"] == 24
    assert rows[0]["condition"] == "kapalı"

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
        patch("app.services.web.weather.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_weather("Ankara")
