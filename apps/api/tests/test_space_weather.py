"""space_weather — NOAA SWPC, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.space_weather import lookup_space_weather, space_weather_url

def test_url_alias() -> None:
    assert space_weather_url() == "https://services.swpc.noaa.gov/products/noaa-scales.json"
    tool = ToolRegistry().get("space_weather")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "space_weather" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("aurora") == "space_weather"
    assert normalize_tool_name("uzay_havasi") == "space_weather"
    assert "space_weather" in BASE_SYSTEM_PROMPT

async def test_olcek_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "0": {
                    "DateStamp": "2026-08-16",
                    "TimeStamp": "11:00:00",
                    "R": {"Scale": "0", "Text": "none"},
                    "S": {"Scale": "0", "Text": "none"},
                    "G": {"Scale": "1", "Text": "minor"},
                },
                "-1": {
                    "DateStamp": "2026-08-16",
                    "R": {"Scale": "1", "Text": "minor"},
                    "S": {"Scale": "0", "Text": "none"},
                    "G": {"Scale": "2", "Text": "moderate"},
                },
                "1": {
                    "DateStamp": "2026-08-17",
                    "R": {"Scale": "0", "Text": "none"},
                    "S": {"Scale": "0", "Text": "none"},
                    "G": {"Scale": "0", "Text": "none"},
                },
            }

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Ok:
            assert "services.swpc.noaa.gov" in url
            return Ok()

    with patch("app.services.web.space_weather.httpx.AsyncClient", Client):
        out = await lookup_space_weather()
    assert out["current"]["geomagnetic"]["scale"] == "1"
    assert out["observed_24h"]["radio_blackout"]["scale"] == "1"

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
        patch("app.services.web.space_weather.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_space_weather()
