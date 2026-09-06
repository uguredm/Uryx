"""prayer_times — Aladhan, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _prayer_times_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.prayer import (
    lookup_prayer_times,
    normalize_prayer_country,
    normalize_prayer_method,
    prayer_times_url,
)

def test_url_ulke_yontem() -> None:
    assert normalize_prayer_country("tr") == "TR"
    assert normalize_prayer_method(None) == 13
    with pytest.raises(ToolExecutionError, match="Ülke"):
        normalize_prayer_country("XX")
    with pytest.raises(ToolExecutionError, match="yöntem"):
        normalize_prayer_method(99)
    url = prayer_times_url("Istanbul", country="TR", method=13, date="2026-08-16")
    assert url.startswith("https://api.aladhan.com/v1/timingsByCity/2026-08-16")
    assert "city=Istanbul" in url
    assert "method=13" in url
    tool = ToolRegistry().get("prayer_times")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "prayer_times" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("namaz") == "prayer_times"
    assert normalize_tool_name("ezan") == "prayer_times"
    assert "prayer_times" in BASE_SYSTEM_PROMPT
    assert _prayer_times_requested("İstanbul namaz vakitleri") is True
    assert _prayer_times_requested("İstanbul hava durumu") is False

def test_intent_filtre_namaz(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Ankara ezan saatleri", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "prayer_times" in names
    assert "weather" not in names

async def test_vakit_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "code": 200,
                "data": {
                    "timings": {
                        "Fajr": "04:12 (EEST)",
                        "Sunrise": "06:01",
                        "Dhuhr": "13:10",
                        "Asr": "16:55",
                        "Maghrib": "19:55",
                        "Isha": "21:25",
                    },
                    "date": {
                        "gregorian": {"date": "16-08-2026"},
                        "hijri": {"date": "22-02-1448"},
                    },
                    "meta": {"method": {"name": "Diyanet İşleri Başkanlığı, Turkey"}},
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
            assert "api.aladhan.com" in url
            return Ok()

    with patch("app.services.web.prayer.httpx.AsyncClient", Client):
        out = await lookup_prayer_times("Istanbul", country="TR", date="2026-08-16")
    assert out["timings"]["fajr"] == "04:12"
    assert out["method"].startswith("Diyanet")

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
        patch("app.services.web.prayer.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_prayer_times("Ankara")
