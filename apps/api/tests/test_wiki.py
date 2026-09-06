"""wiki_lookup — Wikimedia REST, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _filter_tool_schemas, _wiki_lookup_requested
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, UNTRUSTED_TOOL_OUTPUT, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.wiki import lookup_wikipedia, normalize_wiki_lang, wiki_summary_url

def test_url_ve_dil() -> None:
    assert normalize_wiki_lang("EN") == "en"
    assert normalize_wiki_lang("de") == "de"
    assert normalize_wiki_lang("xx") == "tr"
    assert wiki_summary_url("Berlin", lang="de").startswith(
        "https://de.wikipedia.org/api/rest_v1/page/summary/"
    )
    url = wiki_summary_url("Alan Turing", lang="en")
    assert url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/")
    assert "Alan" in url
    with pytest.raises(ToolExecutionError):
        wiki_summary_url("  ")

def test_kayit_alias_ve_prompt() -> None:
    tool = ToolRegistry().get("wiki_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "wiki_lookup" in IDEMPOTENT_TOOLS
    assert "wiki_lookup" in UNTRUSTED_TOOL_OUTPUT
    assert normalize_tool_name("wikipedia") == "wiki_lookup"
    assert normalize_tool_name("ansiklopedi") == "wiki_lookup"
    assert normalize_tool_name("wikipedia_de") == "wiki_lookup"
    langs = next(p.enum for p in tool.parameters if p.name == "lang")
    assert langs == ["tr", "en", "de"]
    assert "wiki_lookup" in BASE_SYSTEM_PROMPT
    assert _wiki_lookup_requested("Atatürk kimdir wikipedia") is True
    assert _wiki_lookup_requested("Bugünün manşetleri") is False

def test_intent_filtre_wiki(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("İstanbul wikipedia maddesi", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "wiki_lookup" in names
    assert "web_search" in names
    assert "web_news" not in names

async def test_ozet_ve_404_opensearch() -> None:
    class Response:
        def __init__(self, status: int, payload: Any, location: str = "") -> None:
            self.status_code = status
            self._payload = payload
            self.headers: ClassVar[dict[str, str]] = {"location": location}

        def json(self) -> Any:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise ToolExecutionError("http")

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            self.calls: list[str] = []

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Response:
            self.calls.append(url)
            if "opensearch" in url:
                return Response(200, ["ist", ["İstanbul"], [""], [""]])
            if "summary/%C4%B0stanbul" in url or "summary/İstanbul" in url:
                return Response(
                    200,
                    {
                        "title": "İstanbul",
                        "extract": "Türkiye'nin en kalabalık kenti.",
                        "description": "şehir",
                        "type": "standard",
                        "content_urls": {
                            "desktop": {"page": "https://tr.wikipedia.org/wiki/%C4%B0stanbul"}
                        },
                    },
                )
            if "summary/ist" in url:
                return Response(404, None)
            return Response(404, None)

    with patch("app.services.web.wiki.httpx.AsyncClient", Client):
        missing = await lookup_wikipedia("ist", lang="tr")
    assert missing["found"] is True
    assert missing["title"] == "İstanbul"
    assert missing.get("resolved_from") == "ist"

async def test_yonlendirme_ozel_host_red() -> None:
    class Response:
        status_code = 302
        headers: ClassVar[dict[str, str]] = {"location": "https://127.0.0.1/secret"}

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

        async def get(self, url: str) -> Response:
            return Response()

    with (
        patch("app.services.web.wiki.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="wikipedia.org"),
    ):
        await lookup_wikipedia("Evil", lang="en")

async def test_backend_wiki(container) -> None:
    async def fake(title: str, *, lang: str = "tr") -> dict[str, object]:
        return {"ok": True, "found": True, "title": title, "lang": lang, "extract": "özet"}

    with patch("app.services.tools.backend_tools.lookup_wikipedia", fake):
        result = await container.backend_tools.execute(
            "wiki_lookup", {"title": "Ankara", "lang": "tr"}
        )
    assert result["found"] is True
    assert result["title"] == "Ankara"
