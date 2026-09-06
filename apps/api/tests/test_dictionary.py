"""dict_lookup — Wiktionary REST, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat.orchestrator import _dict_lookup_requested, _filter_tool_schemas
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, UNTRUSTED_TOOL_OUTPUT, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.dictionary import dict_definition_url, lookup_dictionary, normalize_dict_lang

def test_url_dil_alias() -> None:
    assert normalize_dict_lang("EN") == "en"
    assert normalize_dict_lang("de") == "de"
    assert normalize_dict_lang("xx") == "tr"
    url = dict_definition_url("hello", lang="en")
    assert url.startswith("https://en.wiktionary.org/api/rest_v1/page/definition/")
    with pytest.raises(ToolExecutionError):
        dict_definition_url("  ")
    tool = ToolRegistry().get("dict_lookup")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "dict_lookup" in IDEMPOTENT_TOOLS
    assert "dict_lookup" in UNTRUSTED_TOOL_OUTPUT
    assert normalize_tool_name("sozluk") == "dict_lookup"
    assert normalize_tool_name("wiktionary") == "dict_lookup"
    assert "dict_lookup" in BASE_SYSTEM_PROMPT
    assert _dict_lookup_requested("merhaba ne demek") is True
    assert _dict_lookup_requested("Atatürk kimdir wikipedia") is False

def test_intent_filtre_sozluk(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("merhaba kelime anlamı", schemas, {"web"})
    names = {item["function"]["name"] for item in filtered}
    assert "dict_lookup" in names
    assert "wiki_lookup" not in names

async def test_tanim_ve_yonlendirme_red() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "en": [
                    {
                        "partOfSpeech": "Interjection",
                        "language": "English",
                        "definitions": [{"definition": "A greeting."}],
                    }
                ]
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
            assert "wiktionary.org" in url
            return Ok()

    with patch("app.services.web.dictionary.httpx.AsyncClient", Client):
        out = await lookup_dictionary("hello", lang="en")
    assert out["found"] is True
    assert out["kind"] == "definition"
    assert out["entries"][0]["definitions"][0] == "A greeting."

async def test_yonlendirme_ozel_host_red() -> None:
    class Redirect:
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

        async def get(self, url: str) -> Redirect:
            return Redirect()

    with (
        patch("app.services.web.dictionary.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="wiktionary.org"),
    ):
        await lookup_dictionary("evil", lang="en")

async def test_backend_sozluk(container) -> None:
    async def fake(term: str, *, lang: str = "tr") -> dict[str, object]:
        return {"ok": True, "found": True, "term": term, "lang": lang, "extract": "selam"}

    with patch("app.services.tools.backend_tools.lookup_dictionary", fake):
        result = await container.backend_tools.execute(
            "dict_lookup", {"term": "merhaba", "lang": "tr"}
        )
    assert result["term"] == "merhaba"
