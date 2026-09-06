"""public_holidays — Nager.Date, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _public_holidays_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.holidays import (
    holidays_url,
    lookup_public_holidays,
    normalize_holiday_country,
    normalize_holiday_year,
)

def test_ulke_yil_ve_alias() -> None:
    assert normalize_holiday_country("tr") == "TR"
    assert normalize_holiday_country("UK") == "GB"
    with pytest.raises(ToolExecutionError, match="Ülke"):
        normalize_holiday_country("XX")
    assert 2000 <= normalize_holiday_year(None) <= 2035
    with pytest.raises(ToolExecutionError, match="Yıl"):
        normalize_holiday_year(1999)
    assert holidays_url("TR", 2026) == "https://date.nager.at/api/v3/PublicHolidays/2026/TR"
    tool = ToolRegistry().get("public_holidays")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "public_holidays" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("resmi_tatil") == "public_holidays"
    assert normalize_tool_name("bayram") == "public_holidays"
    assert "public_holidays" in BASE_SYSTEM_PROMPT
    assert _public_holidays_requested("2026 resmi tatiller") is True
    assert _public_holidays_requested("İstanbul hava durumu") is False

def test_intent_filtre_tatil(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Türkiye resmi tatil listesi", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "public_holidays" in names
    assert "web_research" not in names

async def test_liste_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> list[dict[str, Any]]:
            return [
                {
                    "date": "2026-01-01",
                    "localName": "Yılbaşı",
                    "name": "New Year's Day",
                    "global": True,
                    "types": ["Public"],
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
            assert "date.nager.at" in url
            return Ok()

    with patch("app.services.web.holidays.httpx.AsyncClient", Client):
        out = await lookup_public_holidays(country="TR", year=2026)
    assert out["count"] == 1
    assert out["holidays"][0]["local_name"] == "Yılbaşı"

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
        patch("app.services.web.holidays.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_public_holidays(country="DE", year=2026)
