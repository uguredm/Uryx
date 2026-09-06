"""elevation — Open-Meteo DEM, weather rewrite yok, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.elevation import elevation_url, lookup_elevation

def test_url_alias() -> None:
    assert "api.open-meteo.com/v1/elevation" in elevation_url(39.7, 44.3)
    tool = ToolRegistry().get("elevation")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "elevation" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("rakim") == "elevation"
    assert normalize_tool_name("yukseklik") == "elevation"
    assert "elevation" in BASE_SYSTEM_PROMPT

async def test_rakim_ve_yonlendirme() -> None:
    class Geo:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "name": "Ağrı",
                        "country": "Türkiye",
                        "latitude": 39.7,
                        "longitude": 44.3,
                    }
                ]
            }

        def raise_for_status(self) -> None:
            return None

    class Elev:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {"elevation": [1640.0]}

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Geo | Elev:
            if "geocoding" in url:
                return Geo()
            assert "elevation" in url
            return Elev()

    with patch("app.services.web.elevation.httpx.AsyncClient", Client):
        out = await lookup_elevation("Ağrı")
    assert out["elevation_m"] == 1640.0

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
        patch("app.services.web.elevation.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_elevation("Everest")
