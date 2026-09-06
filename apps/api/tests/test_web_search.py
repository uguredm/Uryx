"""web_search site/filetype/timelimit — ağ yok."""

from __future__ import annotations

import pytest
from app.core.errors import ToolExecutionError
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.search import (
    compose_search_query,
    normalize_search_filetype,
    normalize_search_site,
    normalize_search_timelimit,
    result_excluded_by_site,
)

def test_site_genel_alan_ve_yerel_red() -> None:
    assert normalize_search_site("https://www.Wikipedia.org/wiki/X") == "wikipedia.org"
    assert normalize_search_site("") == ""
    with pytest.raises(ToolExecutionError, match="yerel"):
        normalize_search_site("localhost")
    with pytest.raises(ToolExecutionError, match="alan adı"):
        normalize_search_site("not a host")
    with pytest.raises(ToolExecutionError, match="alan adı"):
        normalize_search_site("127.0.0.1")

def test_filetype_ve_pencere() -> None:
    assert normalize_search_filetype(".PDF") == "pdf"
    assert normalize_search_filetype("") == ""
    with pytest.raises(ToolExecutionError, match="filetype"):
        normalize_search_filetype("exe")
    assert normalize_search_timelimit("y") == "y"
    assert normalize_search_timelimit("") is None
    assert normalize_search_timelimit("week") is None

def test_sorgu_operator_birlesir() -> None:
    assert compose_search_query("kedi", site="wikipedia.org", filetype="pdf") == (
        "kedi site:wikipedia.org filetype:pdf"
    )
    assert compose_search_query("kedi", exclude_site="pinterest.com") == (
        "kedi -site:pinterest.com"
    )
    assert compose_search_query("kedi") == "kedi"
    with pytest.raises(ToolExecutionError, match="aynı"):
        compose_search_query("kedi", site="a.com", exclude_site="a.com")
    assert result_excluded_by_site(
        {"url": "https://www.pinterest.com/x"}, "pinterest.com"
    )
    assert not result_excluded_by_site({"url": "https://example.com/x"}, "pinterest.com")

def test_sema_ve_alias() -> None:
    names = {param.name: param for param in ToolRegistry().get("web_search").parameters}
    assert names["region"].default == "tr-tr"
    assert names["timelimit"].enum == ["d", "w", "m", "y"]
    assert "site" in names
    assert "exclude_site" in names
    assert "pdf" in (names["filetype"].enum or [])
    assert normalize_tool_name("internette_ara") == "web_search"
    assert normalize_tool_name("internet_search") == "web_search"
    assert "site=" in BASE_SYSTEM_PROMPT
    assert "elle site:" in BASE_SYSTEM_PROMPT

async def test_backend_site_ve_tur_gecer(container) -> None:
    seen: dict[str, object] = {}

    async def fake_search(
        query: str,
        *,
        max_results: int = 5,
        region: str = "tr-tr",
        timelimit: str | None = None,
        site: str = "",
        filetype: str = "",
        exclude_site: str = "",
    ) -> list[dict[str, str]]:
        seen.update(
            {
                "query": query,
                "max_results": max_results,
                "region": region,
                "timelimit": timelimit,
                "site": site,
                "filetype": filetype,
                "exclude_site": exclude_site,
            }
        )
        return [{"title": query, "summary": "", "url": "https://example.com/a"}]

    container.backend_tools._web_search.search = fake_search  # type: ignore[method-assign]
    result = await container.backend_tools.execute(
        "web_search",
        {
            "query": "kedi",
            "region": "wt-wt",
            "timelimit": "y",
            "site": "wikipedia.org",
            "filetype": "pdf",
            "exclude_site": "pinterest.com",
        },
    )
    assert seen["site"] == "wikipedia.org"
    assert seen["exclude_site"] == "pinterest.com"
    assert seen["filetype"] == "pdf"
    assert seen["timelimit"] == "y"
    assert result["count"] == 1
    assert result["site"] == "wikipedia.org"
