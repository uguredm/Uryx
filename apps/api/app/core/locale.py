"""Request-scoped UI language (D25 default: English)."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.schemas.tools import ToolDefinition

UiLanguage = Literal["tr", "en"]

_ui_language: ContextVar[UiLanguage] = ContextVar("ui_language", default="en")

_ACRONYMS = {
    "cpu": "CPU",
    "gpu": "GPU",
    "ram": "RAM",
    "usb": "USB",
    "sha": "SHA",
    "vscode": "VS Code",
    "wifi": "Wi-Fi",
    "ssid": "SSID",
    "iban": "IBAN",
    "dns": "DNS",
    "doi": "DOI",
    "fx": "FX",
    "mcp": "MCP",
    "tts": "TTS",
    "stt": "STT",
    "rag": "RAG",
    "os": "OS",
    "ip": "IP",
    "uv": "UV",
    "aqi": "AQI",
    "rss": "RSS",
    "osm": "OSM",
    "npm": "npm",
    "pypi": "PyPI",
    "iss": "ISS",
    "llm": "LLM",
    "pid": "PID",
}

_TR_LETTERS = frozenset("çğıöşüÇĞİÖŞÜ")

_TR_ASCII_IMPACT = re.compile(
    r"yoksa|bulunamad|okunur|\bsalt\b|konteyner",
    re.IGNORECASE,
)

def parse_ui_language(raw: str | None) -> UiLanguage:
    """Header / options value → ``tr`` or ``en``."""
    value = (raw or "").strip().lower()
    if value.startswith("tr"):
        return "tr"
    return "en"

def set_ui_language(raw: str | None) -> Token[UiLanguage]:
    """Pin the UI language for this task; return the reset token."""
    return _ui_language.set(parse_ui_language(raw))

def reset_ui_language(token: Token[UiLanguage]) -> None:
    """Restore the previous UI language."""
    _ui_language.reset(token)

def ui_language() -> UiLanguage:
    """Current request/task UI language."""
    return _ui_language.get()

def loc(tr: str, en: str) -> str:
    """Pick Turkish or English copy for the current UI language."""
    return tr if ui_language() == "tr" else en

def has_tr_letters(text: str) -> bool:
    """True if the string contains Turkish-specific letters."""
    return any(ch in _TR_LETTERS for ch in text)

def english_tool_label(name: str) -> str:
    """``open_application`` → ``Open application``; keep CPU/GPU acronyms."""
    words: list[str] = []
    for index, part in enumerate(name.split("_")):
        key = part.lower()
        if key in _ACRONYMS:
            words.append(_ACRONYMS[key])
        elif index == 0:
            words.append(part.capitalize())
        else:
            words.append(part.lower())
    return " ".join(words)

def localize_tool(tool: ToolDefinition) -> ToolDefinition:
    """Copy a tool definition into the current UI language (EN labels; TR unchanged)."""
    if ui_language() == "tr":
        return tool
    from app.schemas.tools import ExecutionTarget

    host = tool.execution is ExecutionTarget.HOST
    description = (
        f"Runs on this Windows PC ({tool.name})."
        if host
        else f"Runs in the Uryx backend ({tool.name})."
    )
    raw_impact = tool.impact or ""
    impact = (
        raw_impact
        if raw_impact
        and not has_tr_letters(raw_impact)
        and not _TR_ASCII_IMPACT.search(raw_impact)
        else ""
    )
    parameters = [
        param.model_copy(
            update={
                "description": (
                    param.name if has_tr_letters(param.description) else param.description
                )
            }
        )
        for param in tool.parameters
    ]
    return tool.model_copy(
        update={
            "display_name": english_tool_label(tool.name),
            "description": description,
            "impact": impact,
            "parameters": parameters,
        }
    )

def language_from_headers(headers: Any) -> str | None:
    """Read ``X-Uryx-Language`` first, then ``Accept-Language``. Missing → None."""
    try:
        raw = headers.get("x-uryx-language") or headers.get("accept-language")
    except Exception:
        return None
    value = str(raw or "").strip()
    return value or None
