"""dns_lookup — Cloudflare DoH, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.dns import dns_lookup_url, lookup_dns, normalize_dns_name

def test_ad_tur_alias() -> None:
    assert normalize_dns_name("Example.COM") == "example.com"
    assert "cloudflare-dns.com/dns-query" in dns_lookup_url("example.com", record_type="MX")
    with pytest.raises(ToolExecutionError, match="Yerel"):
        normalize_dns_name("localhost")
    with pytest.raises(ToolExecutionError, match="ip_lookup"):
        normalize_dns_name("8.8.8.8")
    assert ToolRegistry().get("dns_lookup") is not None
    assert "dns_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("dns") == "dns_lookup"
    assert "dns_lookup" in BASE_SYSTEM_PROMPT

async def test_kayit_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {"Status": 0, "Answer": [{"data": "93.184.216.34"}]}

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
            assert "cloudflare-dns.com" in url
            return Ok()

    with patch("app.services.web.dns.httpx.AsyncClient", Client):
        out = await lookup_dns("example.com", record_type="A")
    assert out["answers"] == ["93.184.216.34"]

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
        patch("app.services.web.dns.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_dns("example.com")
