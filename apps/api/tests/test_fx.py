"""fx_rate — Frankfurter, sabit host, ağ yok."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _fx_rate_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.fx import fx_rate_url, lookup_fx_rate, normalize_fx_code

def test_kod_ve_url() -> None:
    assert normalize_fx_code("usd") == "USD"
    assert normalize_fx_code("tl") == "TRY"
    assert fx_rate_url("USD", "TRY") == "https://api.frankfurter.dev/v2/rate/USD/TRY"
    with pytest.raises(ToolExecutionError, match="desteklenmiyor"):
        normalize_fx_code("BTC")

def test_kayit_alias_prompt() -> None:
    tool = ToolRegistry().get("fx_rate")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "fx_rate" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("doviz") == "fx_rate"
    assert normalize_tool_name("kur") == "fx_rate"
    assert "fx_rate" in BASE_SYSTEM_PROMPT
    assert _fx_rate_requested("100 dolar kaç TL") is True
    assert _fx_rate_requested("güncel euro kuru") is True
    assert _fx_rate_requested("Bugünün manşetleri") is False

def test_intent_filtre_fx(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("100 dolar kaç TL", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert names == {"fx_rate"} or "fx_rate" in names
    assert "web_research" not in names

async def test_ceviri_ve_yonlendirme_red() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, object]:
            return {"date": "2026-08-15", "base": "USD", "quote": "TRY", "rate": 33.5}

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
            assert "api.frankfurter.dev" in url
            return Ok()

    with patch("app.services.web.fx.httpx.AsyncClient", Client):
        out = await lookup_fx_rate(base="USD", quote="TRY", amount=2)
    assert out["converted"] == 67.0
    assert out["rate"] == 33.5

async def test_yonlendirme_kabul_edilmez() -> None:
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
        patch("app.services.web.fx.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_fx_rate(base="EUR", quote="USD")

async def test_backend_fx(container) -> None:
    async def fake(*, base: str, quote: str, amount: float = 1.0) -> dict[str, object]:
        return {"ok": True, "base": base, "quote": quote, "amount": amount, "converted": 10}

    with patch("app.services.tools.backend_tools.lookup_fx_rate", fake):
        result = await container.backend_tools.execute(
            "fx_rate", {"base": "USD", "quote": "TRY", "amount": 3}
        )
    assert result["converted"] == 10
