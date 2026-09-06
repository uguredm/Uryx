"""pollen — Open-Meteo CAMS, air_quality rewrite yok, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.pollen import lookup_pollen, pollen_url

def test_url_alias() -> None:
    assert "air-quality-api.open-meteo.com" in pollen_url(41.01, 28.97)
    assert "grass_pollen" in pollen_url(41.01, 28.97)
    assert ToolRegistry().get("pollen") is not None
    assert "pollen" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("polen") == "pollen"
    assert "pollen" in BASE_SYSTEM_PROMPT

async def test_yogunluk_ve_yonlendirme() -> None:
    class Geo:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "name": "İstanbul",
                        "country": "Türkiye",
                        "latitude": 41.01,
                        "longitude": 28.97,
                    }
                ]
            }

        def raise_for_status(self) -> None:
            return None

    class Pol:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "current": {
                    "time": "2026-08-16T14:00",
                    "alder_pollen": 0,
                    "birch_pollen": 1,
                    "grass_pollen": 12,
                    "mugwort_pollen": 0,
                    "olive_pollen": 3,
                    "ragweed_pollen": 0,
                }
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

        async def get(self, url: str) -> Geo | Pol:
            if "geocoding" in url:
                return Geo()
            assert "air-quality-api.open-meteo.com" in url
            return Pol()

    with patch("app.services.web.pollen.httpx.AsyncClient", Client):
        out = await lookup_pollen("İstanbul")
    assert out["grass"] == 12
    assert out["olive"] == 3

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
        patch("app.services.web.pollen.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_pollen("Ankara")
