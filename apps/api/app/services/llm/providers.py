"""Bulut LLM sağlayıcı kataloğu — anahtar / model adından algılama."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import ValidationError

@dataclass(frozen=True)
class CloudProvider:
    """OpenAI uyumlu HTTPS sohbet uç noktası."""

    id: str
    label: str
    url: str
    default_model: str

PROVIDERS: dict[str, CloudProvider] = {
    "gemini": CloudProvider(
        "gemini",
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3-flash-preview",
    ),
    "openai": CloudProvider(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1",
        "gpt-4o-mini",
    ),
    "openrouter": CloudProvider(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "openai/gpt-4o-mini",
    ),
    "groq": CloudProvider(
        "groq",
        "Groq",
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
    ),
    "deepseek": CloudProvider(
        "deepseek",
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "deepseek-chat",
    ),
    "xai": CloudProvider(
        "xai",
        "xAI",
        "https://api.x.ai/v1",
        "grok-2-latest",
    ),
    "mistral": CloudProvider(
        "mistral",
        "Mistral",
        "https://api.mistral.ai/v1",
        "mistral-small-latest",
    ),
    "together": CloudProvider(
        "together",
        "Together AI",
        "https://api.together.xyz/v1",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ),
    "fireworks": CloudProvider(
        "fireworks",
        "Fireworks",
        "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
    ),
}

_CURSOR_HINT = (
    "Cursor hesabındaki token Uryx sohbetinde çalışmaz. "
    "Google AI Studio (AIza…), OpenAI (sk-…), OpenRouter (sk-or-…) "
    "veya xAI (xai-…) anahtarı kullanın."
)
_ANTHROPIC_HINT = (
    "Claude (Anthropic) doğrudan OpenAI uyumlu değil. "
    "OpenRouter anahtarı (sk-or-...) ve model adı olarak anthropic/claude-… kullanın."
)

def label_for(provider_id: str) -> str:
    """UI / hata metni için sağlayıcı etiketi."""
    known = PROVIDERS.get(provider_id)
    return known.label if known else "Bulut model"

def provider_by_id(provider_id: str) -> CloudProvider:
    """Katalog kaydı; bilinmeyende Gemini (eski varsayılan)."""
    return PROVIDERS.get(provider_id, PROVIDERS["gemini"])

def detect_cloud_provider(api_key: str, model: str = "") -> CloudProvider:
    """Anahtar öneki ve isteğe bağlı model adından sağlayıcı seçer.

    Anahtarı başka bir servise deneme isteği göndermez.
    """
    key = api_key.strip()
    catalog = model.strip().lower()
    lowered = key.lower()
    if "cursor" in lowered or lowered.startswith(("crsr_", "cur_")):
        raise ValidationError(_CURSOR_HINT)

    if catalog.startswith("claude"):
        raise ValidationError(_ANTHROPIC_HINT)
    if catalog.startswith("gemini") or catalog.startswith("models/gemini"):
        return PROVIDERS["gemini"]
    if catalog.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
        return PROVIDERS["openai"]
    if catalog.startswith("deepseek"):
        return PROVIDERS["deepseek"]
    if catalog.startswith("grok"):
        return PROVIDERS["xai"]
    if catalog.startswith(("mistral", "codestral", "pixtral", "ministral")):
        return PROVIDERS["mistral"]
    if "/" in catalog and not catalog.startswith("accounts/"):
        return PROVIDERS["openrouter"]
    if catalog.startswith("accounts/fireworks"):
        return PROVIDERS["fireworks"]
    if catalog.startswith(("meta-llama/", "Qwen/", "mistralai/")):
        return PROVIDERS["together"]

    if key.startswith("sk-or-"):
        return PROVIDERS["openrouter"]
    if key.startswith("sk-ant-"):
        raise ValidationError(_ANTHROPIC_HINT)
    if key.startswith("gsk_"):
        return PROVIDERS["groq"]
    if key.startswith("AIza"):
        return PROVIDERS["gemini"]
    if key.startswith("xai-"):
        return PROVIDERS["xai"]
    if key.startswith("fw_"):
        return PROVIDERS["fireworks"]
    if key.startswith(("sk-proj-", "sk-svcacct-", "sk-")):
        return PROVIDERS["openai"]

    return PROVIDERS["gemini"]
