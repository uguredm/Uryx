"""OpenAI-uyumlu bulut sohbet istemcisi (Gemini, OpenAI, Groq, OpenRouter, …)."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.services.llm.providers import label_for
from app.services.llm.vllm_client import VLLMClient

class GeminiClient(VLLMClient):
    """Yerel llama uzantıları olmadan OpenAI chat completions protokolü."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            settings,
            client=client,
            base_url=settings.gemini_url,
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            provider_name=label_for(settings.cloud_provider),
            vllm_extensions=False,
            request_timeout=settings.gemini_request_timeout,
        )
