"""earthquakes — USGS FDSN, sabit host, ağ yok."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _earthquakes_requested, _filter_tool_schemas
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.earthquakes import (
    earthquakes_url,
    lookup_earthquakes,
    normalize_quake_region,
)

def test_url_bolge_alias() -> None:
    assert normalize_quake_region("turkey") == "tr"
    assert normalize_quake_region("global") == "world"
    with pytest.raises(ToolExecutionError, match="Bölge"):
        normalize_quake_region("xx")
    now = datetime(2026, 8, 16, tzinfo=UTC)
    tr = earthquakes_url(region="tr", minmagnitude=3, days=2, limit=8, now=now)
    assert tr.startswith("https://earthquake.usgs.gov/fdsnws/event/1/query")
    assert "minlatitude=35.8" in tr
    assert "format=geojson" in tr
    world = earthquakes_url(region="world", days=1, now=now)
    assert "minlatitude" not in world
    assert "minmagnitude=5" in world
    tool = ToolRegistry().get("earthquakes")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "earthquakes" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("deprem") == "earthquakes"
    assert normalize_tool_name("sismik") == "earthquakes"
    assert "earthquakes" in BASE_SYSTEM_PROMPT
    assert _earthquakes_requested("Türkiye'de son depremler") is True
    assert _earthquakes_requested("deprem haberi manşet") is False

def test_intent_filtre_deprem(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("son depremler Türkiye'de", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "earthquakes" in names
    assert "web_news" not in names

async def test_liste_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "features": [
                    {
                        "properties": {
                            "mag": 4.2,
                            "place": "10 km E of Izmir",
                            "time": 1_755_000_000_000,
                            "tsunami": 0,
                            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/x",
                        },
                        "geometry": {"coordinates": [27.1, 38.4, 10.0]},
                    }
                ]
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
            assert "earthquake.usgs.gov" in url
            return Ok()

    with patch("app.services.web.earthquakes.httpx.AsyncClient", Client):
        out = await lookup_earthquakes(region="tr", days=2)
    assert out["count"] == 1
    assert out["events"][0]["magnitude"] == 4.2
    assert out["events"][0]["depth_km"] == 10.0

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
        patch("app.services.web.earthquakes.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_earthquakes(region="world")
