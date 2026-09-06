"""doi_lookup — Crossref, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.doi import doi_url, lookup_doi, normalize_doi

def test_doi_normalize_alias() -> None:
    assert normalize_doi("https://doi.org/10.1038/nphys1170") == "10.1038/nphys1170"
    assert normalize_doi("doi:10.1038/nphys1170") == "10.1038/nphys1170"
    assert "api.crossref.org/works/10.1038/" in doi_url("10.1038/nphys1170")
    with pytest.raises(ToolExecutionError):
        normalize_doi("not-a-doi")
    tool = ToolRegistry().get("doi_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "doi_lookup" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("doi") == "doi_lookup"
    assert normalize_tool_name("crossref") == "doi_lookup"
    assert "doi_lookup" in BASE_SYSTEM_PROMPT

async def test_kayit_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "status": "ok",
                "message": {
                    "DOI": "10.1038/nphys1170",
                    "title": ["A paper"],
                    "type": "journal-article",
                    "publisher": "Springer Nature",
                    "container-title": ["Nature Physics"],
                    "URL": "https://doi.org/10.1038/nphys1170",
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "published-print": {"date-parts": [[2008]]},
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
            assert "api.crossref.org" in url
            return Ok()

    with patch("app.services.web.doi.httpx.AsyncClient", Client):
        out = await lookup_doi("10.1038/nphys1170")
    assert out["found"] is True
    assert out["title"] == "A paper"
    assert out["authors"] == ["Ada Lovelace"]
    assert out["year"] == 2008

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
        patch("app.services.web.doi.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_doi("10.1038/nphys1170")
