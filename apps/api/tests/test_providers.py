"""Bulut sağlayıcı algılama."""

from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.services.llm.providers import detect_cloud_provider

def test_openai_sk_proj() -> None:
    found = detect_cloud_provider("sk-proj-abc123")
    assert found.id == "openai"
    assert found.url.endswith("/v1")
    assert found.default_model == "gpt-4o-mini"

def test_openrouter_sk_or() -> None:
    found = detect_cloud_provider("sk-or-v1-abc")
    assert found.id == "openrouter"

def test_groq_gsk() -> None:
    found = detect_cloud_provider("gsk_abc")
    assert found.id == "groq"

def test_gemini_aiza() -> None:
    found = detect_cloud_provider("AIzaSyDummy")
    assert found.id == "gemini"

def test_model_name_overrides_ambiguous_key() -> None:
    found = detect_cloud_provider("sk-abc", "deepseek-chat")
    assert found.id == "deepseek"

def test_unknown_key_defaults_to_gemini() -> None:
    found = detect_cloud_provider("ui-test-key-9f3a")
    assert found.id == "gemini"

def test_anthropic_rejected() -> None:
    with pytest.raises(ValidationError, match="OpenRouter"):
        detect_cloud_provider("sk-ant-api03-abc")

def test_cursor_token_rejected() -> None:
    with pytest.raises(ValidationError, match="Cursor"):
        detect_cloud_provider("crsr_abc", "gemini-3-flash-preview")
