"""postal_lookup — Zippopotam.us, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _postal_lookup_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.postal import lookup_postal, normalize_postal_code, postal_url

def test_url_kod_alias() -> None:
    assert postal_url("34000", country="TR") == "https://api.zippopotam.us/tr/34000"
    assert normalize_postal_code("34 000") == "34000"
    with pytest.raises(ToolExecutionError):
        normalize_postal_code("x")
    tool = ToolRegistry().get("postal_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "postal_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("posta_kodu") == "postal_lookup"
    assert normalize_tool_name("zipcode") == "postal_lookup"
    assert "postal_lookup" in BASE_SYSTEM_PROMPT
    assert _postal_lookup_requested("34000 posta kodu neresi") is True
    assert _postal_lookup_requested("Türkiye başkenti neresi") is False

def test_intent_filtre_posta(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("34000 posta kodu neresi", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "postal_lookup" in names
    assert "country_info" not in names

async def test_yer_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "post code": "34000",
                "country": "Turkey",
                "places": [
                    {
                        "place name": "Fatih",
                        "state": "Istanbul",
                        "state abbreviation": "34",
                        "latitude": "41.0186",
                        "longitude": "28.9647",
                    }
                ],
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
            assert "api.zippopotam.us" in url
            return Ok()

    with patch("app.services.web.postal.httpx.AsyncClient", Client):
        out = await lookup_postal("34000", country="TR")
    assert out["found"] is True
    assert out["places"][0]["place"] == "Fatih"

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
        patch("app.services.web.postal.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_postal("10115", country="DE")
