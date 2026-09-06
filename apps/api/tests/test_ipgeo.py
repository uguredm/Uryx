"""ip_lookup — ipwho.is, özel IP yok, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.ipgeo import ip_lookup_url, lookup_ip, normalize_public_ip

def test_genel_ip_alias() -> None:
    assert normalize_public_ip("8.8.8.8") == "8.8.8.8"
    assert ip_lookup_url("1.1.1.1") == "https://ipwho.is/1.1.1.1"
    with pytest.raises(ToolExecutionError, match="Özel"):
        normalize_public_ip("192.168.1.1")
    with pytest.raises(ToolExecutionError, match="yerel"):
        normalize_public_ip("127.0.0.1")
    tool = ToolRegistry().get("ip_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert "ip_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("ipwhois") == "ip_lookup"
    assert "ip_lookup" in BASE_SYSTEM_PROMPT

async def test_konum_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "success": True,
                "ip": "8.8.8.8",
                "country": "United States",
                "country_code": "US",
                "region": "California",
                "city": "Mountain View",
                "connection": {"asn": 15169, "org": "Google LLC"},
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
            assert "ipwho.is" in url
            return Ok()

    with patch("app.services.web.ipgeo.httpx.AsyncClient", Client):
        out = await lookup_ip("8.8.8.8")
    assert out["city"] == "Mountain View"
    assert out["asn"] == 15169

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
        patch("app.services.web.ipgeo.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_ip("1.1.1.1")
