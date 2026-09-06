"""Lookup katalog — LOW/BACKEND/idempotent/untrusted + when-not + alias."""

from __future__ import annotations

from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.chat import orchestrator as orch
from app.services.chat.orchestrator import (
    CORE_EVERYDAY_TOOLS,
    LOOKUP_TOOLS,
    WEB_TOOL_NAMES,
    _browser_open_requested,
    _filter_tool_schemas,
    _schema_category_not_web,
    _tool_schema_tokens,
)
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import (
    IDEMPOTENT_TOOLS,
    TOOL_NAME_ALIASES,
    UNTRUSTED_TOOL_OUTPUT,
    normalize_tool_name,
)
from app.services.tools.registry import ToolRegistry

LOOKUP_WEB = (
    "wiki_lookup",
    "dict_lookup",
    "fx_rate",
    "weather",
    "public_holidays",
    "air_quality",
    "earthquakes",
    "country_info",
    "prayer_times",
    "sun_times",
    "postal_lookup",
    "iss_now",
    "space_weather",
    "doi_lookup",
    "elevation",
    "pypi_lookup",
    "ip_lookup",
    "food_barcode",
    "npm_lookup",
    "dns_lookup",
    "pollen",
)

ASCII_ALIASES = {
    "wikipedia": "wiki_lookup",
    "sozluk": "dict_lookup",
    "doviz": "fx_rate",
    "hava_kirliligi": "air_quality",
    "pm25": "air_quality",
    "namaz_vakitleri": "prayer_times",
    "posta": "postal_lookup",
    "zip": "postal_lookup",
    "gtin": "food_barcode",
    "upc": "food_barcode",
    "nslookup": "dns_lookup",
    "dig": "dns_lookup",
    "ip_adresi": "ip_lookup",
    "iban": "iban_check",
    "iban_dogrula": "iban_check",
}

def test_web_lookup_allowlist_ve_when_not() -> None:
    registry = ToolRegistry()
    names = {schema["function"]["name"] for schema in registry.openai_schemas()}
    for name in LOOKUP_WEB:
        tool = registry.get(name)
        assert tool.risk is RiskLevel.LOW, name
        assert tool.execution is ExecutionTarget.BACKEND, name
        assert name in IDEMPOTENT_TOOLS, name
        assert name in UNTRUSTED_TOOL_OUTPUT, name
        assert name in names, name
        assert "Ne zaman değil" in tool.description, name
        assert name in BASE_SYSTEM_PROMPT, name

def test_ascii_alias_ve_iban_yerel() -> None:
    for alias, canonical in ASCII_ALIASES.items():
        assert TOOL_NAME_ALIASES[alias] == canonical
        assert normalize_tool_name(alias) == canonical
    tool = ToolRegistry().get("iban_check")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert tool.category == "system"
    assert "iban_check" in IDEMPOTENT_TOOLS
    assert "iban_check" not in UNTRUSTED_TOOL_OUTPUT
    assert "iban_check" in BASE_SYSTEM_PROMPT
    assert "Ne zaman değil" in tool.description

def test_web_denylist_registry_ile_ayni() -> None:
    registry = ToolRegistry()
    web = {tool.name for tool in registry.enabled() if tool.category == "web"}
    assert web == set(WEB_TOOL_NAMES)
    assert web == set(LOOKUP_TOOLS)
    assert "iban_check" not in web
    for name in ("pollen", "iss_now", "open_external_url", "food_barcode"):
        assert name in web
        assert _schema_category_not_web({"function": {"name": name}}) is False
    assert _schema_category_not_web({"function": {"name": "iban_check"}}) is True
    assert _schema_category_not_web({"function": {"name": "calculate"}}) is True

def test_belirsiz_tur_cekirdek_sema_40_degil() -> None:
    schemas = ToolRegistry().openai_schemas()
    assert len(schemas) > 30
    filtered = _filter_tool_schemas("yarın ne yapmalıyım", schemas, None)
    names = {item["function"]["name"] for item in filtered}
    assert names == set(CORE_EVERYDAY_TOOLS)
    assert len(names) <= 8
    assert "iss_now" not in names
    assert "pollen" not in names
    assert "iban_check" in names
    assert "web_search" in names
    assert _tool_schema_tokens(filtered) < 2000
    assert _tool_schema_tokens(filtered) < _tool_schema_tokens(schemas) // 2

def test_web_filtre_yeni_lookup_sizmaz(container) -> None:
    schemas = container.registry.openai_schemas(categories={"web"})
    filtered = _filter_tool_schemas("Manifest'in son şarkısı ne?", schemas, {"web"})
    assert {item["function"]["name"] for item in filtered} == {"web_research"}

def test_forma_yaz_click_form_dalinda_open_dalina_sizmaz() -> None:
    form_requested = getattr(orch, "_browser_form_requested")
    assert form_requested("şu forma adımı yaz") is True
    assert form_requested("arama kutusuna merhaba yaz") is True
    assert form_requested("Spotify uygulamasını aç") is False
    assert _browser_open_requested("Spotify uygulamasını aç") is True
    schemas = ToolRegistry().openai_schemas(categories={"web"})
    form = {
        item["function"]["name"]
        for item in _filter_tool_schemas("şu forma adımı yaz", schemas, {"web"})
    }
    assert form == {
        "browser_list_controls",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_open",
        "browser_read_page",
    }
    opened = {
        item["function"]["name"]
        for item in _filter_tool_schemas("Spotify uygulamasını aç", schemas, {"web"})
    }
    assert opened == {"web_search", "browser_open", "browser_read_page", "web_fetch"}
    assert "browser_click" not in opened
    assert "browser_click" not in CORE_EVERYDAY_TOOLS
