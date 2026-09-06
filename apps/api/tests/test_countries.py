"""country_info — REST Countries, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _country_info_requested, _filter_tool_schemas
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.countries import country_alpha_url, country_name_url, lookup_country

def test_url_alias() -> None:
    assert "restcountries.com/v3.1/name/" in country_name_url("Türkiye")
    assert "/alpha/TR?" in country_alpha_url("tr")
    assert "/alpha/DEU?" in country_alpha_url("deu")
    with pytest.raises(ToolExecutionError):
        country_name_url("  ")
    tool = ToolRegistry().get("country_info")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "country_info" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("baskent") == "country_info"
    assert normalize_tool_name("ulke") == "country_info"
    assert "country_info" in BASE_SYSTEM_PROMPT
    assert _country_info_requested("Türkiye'nin başkenti neresi") is True
    assert _country_info_requested("2026 resmi tatiller") is False

def test_intent_filtre_ulke(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Almanya başkenti neresi", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "country_info" in names
    assert "wiki_lookup" not in names

async def test_kayit_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> list[dict[str, Any]]:
            return [
                {
                    "name": {"common": "Turkey", "official": "Republic of Türkiye"},
                    "cca2": "TR",
                    "cca3": "TUR",
                    "capital": ["Ankara"],
                    "region": "Asia",
                    "subregion": "Western Asia",
                    "population": 85_000_000,
                    "area": 783562,
                    "currencies": {"TRY": {"name": "Turkish lira"}},
                    "languages": {"tur": "Turkish"},
                    "timezones": ["UTC+03:00"],
                    "borders": ["GRC", "BGR"],
                    "flags": {"png": "https://flagcdn.com/w320/tr.png"},
                }
            ]

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
            assert "restcountries.com" in url
            return Ok()

    with patch("app.services.web.countries.httpx.AsyncClient", Client):
        out = await lookup_country("Türkiye")
    assert out["found"] is True
    assert out["countries"][0]["capital"] == ["Ankara"]
    assert out["countries"][0]["cca2"] == "TR"

async def test_yonlendirme_red() -> None:
    class Redirect:
        status_code = 302
        headers: ClassVar[dict[str, str]] = {"location": "https://evil.example/"}

        def json(self) -> list[str]:
            return []

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
        patch("app.services.web.countries.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_country("DE")
