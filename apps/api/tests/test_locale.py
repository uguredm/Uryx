"""UI language context — D25 default English; pytest pins Turkish via conftest."""

from __future__ import annotations

from app.core.errors import NotFoundError, ToolExecutionError
from app.core.locale import (
    english_tool_label,
    loc,
    parse_ui_language,
    set_ui_language,
    ui_language,
)
from app.services.llm.prompts import build_system_prompt
from app.services.tools.registry import ToolRegistry

def test_parse_ui_language_defaults_to_english() -> None:
    assert parse_ui_language(None) == "en"
    assert parse_ui_language("") == "en"
    assert parse_ui_language("en-US") == "en"
    assert parse_ui_language("tr") == "tr"
    assert parse_ui_language("tr-TR") == "tr"

def test_loc_follows_context() -> None:
    token = set_ui_language("en")
    try:
        assert ui_language() == "en"
        assert loc("Kayıt bulunamadı.", "Record not found.") == "Record not found."
        assert NotFoundError().user_message == "Record not found."
        assert ToolExecutionError().user_message == "Tool failed."
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)

def test_english_system_prompt_does_not_force_turkish() -> None:
    token = set_ui_language("en")
    try:
        prompt = build_system_prompt(language="en")
        assert "Always reply in English" in prompt
        assert "Her zaman Türkçe cevap ver" not in prompt
        assert "CURRENT TIME (Europe/Istanbul)" in prompt
        assert "weather" in prompt
        assert "wiki_lookup" in prompt
        assert "Do not type site:" in prompt
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)

def test_turkish_system_prompt_still_pins_relative_dates() -> None:
    token = set_ui_language("tr")
    try:
        prompt = build_system_prompt(language="tr")
        assert "Her zaman Türkçe cevap ver" in prompt
        assert "GÜNCEL ZAMAN (Europe/Istanbul)" in prompt
        assert "Always reply in English" not in prompt
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)

def test_tool_registry_lists_english_labels() -> None:
    token = set_ui_language("en")
    try:
        tool = next(t for t in ToolRegistry().all() if t.name == "open_application")
        assert tool.display_name == "Open application"
        assert "ç" not in tool.description.lower()
        assert "ğ" not in tool.description.lower()
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)

def test_english_tool_label_keeps_acronyms() -> None:
    assert english_tool_label("open_application") == "Open application"
    assert english_tool_label("get_cpu_usage") == "Get CPU usage"
    assert english_tool_label("open_vscode") == "Open VS Code"

def test_policy_and_wiki_errors_follow_ui_language() -> None:
    from app.services.tools.policy import ConfirmDecision, last_tool_round_hint, rejection_message
    from app.services.web.wiki import wiki_summary_url

    token = set_ui_language("en")
    try:
        assert "timed out" in rejection_message(ConfirmDecision(approved=False, reason="timeout")).lower()
        hint = last_tool_round_hint(0, 1)
        assert hint is not None
        assert "English" in hint
        assert "Türkçe" not in hint
        try:
            wiki_summary_url("")
            raise AssertionError("expected empty title to fail")
        except ToolExecutionError as exc:
            assert "cannot be empty" in exc.user_message.lower()
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)

def test_direct_action_copy_follows_ui_language() -> None:
    from app.services.chat.orchestrator import _direct_action_response

    executed = [
        {
            "tool_name": "copy_selected_text",
            "success": True,
            "result": {"copied": True, "empty": False},
        }
    ]
    token = set_ui_language("en")
    try:
        text = _direct_action_response("kopyala", executed) or ""
        assert "clipboard" in text.lower()
        assert not any(ch in text for ch in "çğıöşüÇĞİÖŞÜ")
    finally:
        from app.core.locale import reset_ui_language

        reset_ui_language(token)
    assert "kopyaladım" in (_direct_action_response("kopyala", executed) or "")
