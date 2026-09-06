"""pypi_lookup — PyPI JSON, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.pypi import lookup_pypi, normalize_pypi_name, pypi_url

def test_ad_url_alias() -> None:
    assert normalize_pypi_name("httpx") == "httpx"
    assert pypi_url("httpx") == "https://pypi.org/pypi/httpx/json"
    with pytest.raises(ToolExecutionError):
        normalize_pypi_name("../evil")
    tool = ToolRegistry().get("pypi_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "pypi_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("pypi") == "pypi_lookup"
    assert "pypi_lookup" in BASE_SYSTEM_PROMPT
    assert "ücretli kripto" in BASE_SYSTEM_PROMPT

async def test_paket_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "info": {
                    "name": "httpx",
                    "version": "0.28.1",
                    "summary": "HTTP client",
                    "license": "BSD",
                    "home_page": "https://www.python-httpx.org",
                    "package_url": "https://pypi.org/project/httpx/",
                    "requires_python": ">=3.8",
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

        async def get(self, url: str) -> Ok:
            assert "pypi.org/pypi/httpx/json" in url
            return Ok()

    with patch("app.services.web.pypi.httpx.AsyncClient", Client):
        out = await lookup_pypi("httpx")
    assert out["found"] is True
    assert out["version"] == "0.28.1"

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
        patch("app.services.web.pypi.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_pypi("ruff")
