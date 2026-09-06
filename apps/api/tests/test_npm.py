"""npm_lookup — registry.npmjs.org, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.npm import lookup_npm, normalize_npm_name, npm_url

def test_ad_alias() -> None:
    assert normalize_npm_name("react") == "react"
    assert normalize_npm_name("@types/node") == "@types/node"
    assert npm_url("react") == "https://registry.npmjs.org/react"
    with pytest.raises(ToolExecutionError):
        normalize_npm_name("../evil")
    assert ToolRegistry().get("npm_lookup") is not None
    assert "npm_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("npm") == "npm_lookup"
    assert "npm_lookup" in BASE_SYSTEM_PROMPT

async def test_paket_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "name": "react",
                "description": "UI library",
                "dist-tags": {"latest": "19.0.0"},
                "versions": {"19.0.0": {"license": "MIT", "description": "UI library"}},
                "homepage": "https://react.dev",
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
            assert "registry.npmjs.org" in url
            return Ok()

    with patch("app.services.web.npm.httpx.AsyncClient", Client):
        out = await lookup_npm("react")
    assert out["version"] == "19.0.0"

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
        patch("app.services.web.npm.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_npm("vue")
