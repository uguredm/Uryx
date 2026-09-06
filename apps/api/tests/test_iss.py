"""iss_now — Where the ISS at, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.iss import iss_now_url, lookup_iss_now

def test_url_alias() -> None:
    assert iss_now_url() == "https://api.wheretheiss.at/v1/satellites/25544"
    tool = ToolRegistry().get("iss_now")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "iss_now" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("iss") == "iss_now"
    assert normalize_tool_name("uzay_istasyonu") == "iss_now"
    assert "iss_now" in BASE_SYSTEM_PROMPT

async def test_konum_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "name": "iss",
                "id": 25544,
                "latitude": 41.0,
                "longitude": 29.0,
                "altitude": 420.1,
                "velocity": 27600,
                "visibility": "daylight",
                "timestamp": 1_755_000_000,
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
            assert "api.wheretheiss.at" in url
            return Ok()

    with patch("app.services.web.iss.httpx.AsyncClient", Client):
        out = await lookup_iss_now()
    assert out["latitude"] == 41.0
    assert out["norad_id"] == 25544

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
        patch("app.services.web.iss.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_iss_now()
