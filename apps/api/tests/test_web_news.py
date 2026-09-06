"""web_news bölge / kaynak / alias — ağ yok."""

from __future__ import annotations

from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.search import (
    NEWS_REGIONS,
    filter_news_by_source,
    news_item_matches_source,
    normalize_news_region,
    normalize_news_safesearch,
    normalize_news_timelimit,
)

def test_bolge_allowlist_ve_bilinmeyen() -> None:
    assert normalize_news_region("TR-TR") == "tr-tr"
    assert normalize_news_region("wt-wt") == "wt-wt"
    assert normalize_news_region("xx-xx", default="tr-tr") == "tr-tr"
    assert normalize_news_region(None) == "wt-wt"
    assert set(NEWS_REGIONS) == {"tr-tr", "wt-wt", "us-en", "uk-en", "de-de"}

def test_safesearch_ve_pencere() -> None:
    assert normalize_news_safesearch("OFF") == "off"
    assert normalize_news_safesearch("maybe") == "moderate"
    assert normalize_news_timelimit("d") == "d"
    assert normalize_news_timelimit("year", default="w") == "w"

def test_kaynak_host_ve_yayin_adi() -> None:
    aa = {
        "title": "Ankara",
        "url": "https://www.aa.com.tr/tr/gundem/x",
        "source": "Anadolu Ajansı",
    }
    reuters = {
        "title": "World",
        "url": "https://www.reuters.com/world/x",
        "source": "Reuters",
    }
    assert news_item_matches_source(aa, "aa.com.tr")
    assert news_item_matches_source(aa, "anadolu")
    assert not news_item_matches_source(aa, "reuters")
    filtered = filter_news_by_source([aa, reuters], "reuters")
    assert [item["source"] for item in filtered] == ["Reuters"]
    assert filter_news_by_source([aa], "") == [aa]

def test_sema_varsayilan_ve_when_not() -> None:
    tool = ToolRegistry().get("web_news")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    names = {param.name: param for param in tool.parameters}
    assert names["region"].default == "tr-tr"
    assert names["region"].enum == ["tr-tr", "wt-wt", "us-en", "uk-en", "de-de"]
    assert names["safesearch"].default == "moderate"
    assert "source" in names
    assert "Ne zaman değil" in tool.description
    assert "web_search" in tool.description

def test_turkce_alias_ve_prompt() -> None:
    for alias in ("haberler", "manset", "gundem", "headlines", "get_news", "haber_ara"):
        assert normalize_tool_name(alias) == "web_news"
    assert "region=tr-tr" in BASE_SYSTEM_PROMPT
    assert "Ansiklopedi" in BASE_SYSTEM_PROMPT

async def test_backend_bolge_ve_kaynak_gecer(container) -> None:
    seen: dict[str, object] = {}

    async def fake_news(
        query: str,
        *,
        max_results: int = 10,
        timelimit: str = "m",
        region: str = "wt-wt",
        safesearch: str = "moderate",
        source: str = "",
    ) -> list[dict[str, str]]:
        seen.update(
            {
                "query": query,
                "max_results": max_results,
                "timelimit": timelimit,
                "region": region,
                "safesearch": safesearch,
                "source": source,
            }
        )
        return [
            {
                "title": query,
                "summary": "özet",
                "url": "https://www.aa.com.tr/tr/x",
                "published": "2026-08-16",
                "source": "AA",
            }
        ]

    container.backend_tools._web_search.news = fake_news  # type: ignore[method-assign]
    result = await container.backend_tools.execute(
        "web_news",
        {
            "query": "Ankara",
            "timelimit": "d",
            "region": "tr-tr",
            "safesearch": "on",
            "source": "aa.com.tr",
        },
    )
    assert seen["region"] == "tr-tr"
    assert seen["source"] == "aa.com.tr"
    assert seen["safesearch"] == "on"
    assert result["count"] == 1
    assert result["region"] == "tr-tr"
    assert result["source"] == "aa.com.tr"
