"""Policy router for local-first inference with an optional Gemini escalation."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.core.logging import get_logger
from app.services.llm.base import ChatMessage, CompletionResult, LLMClient, StreamDelta

logger = get_logger(__name__)

_CLOUD_INTENT = re.compile(
    r"\b(araştır|arastir|incele|analiz|karşılaştır|karsilastir|planla|tasarla|"
    r"mimari|strateji|neden|nasıl|nasil|hata ayıkla|debug|güncel|guncel|"
    r"en son|latest|kanıt|kanit|kaynakları tara|kaynaklari tara)\w*\b",
    re.IGNORECASE,
)
_PRIVATE_TOOLS = {
    "clipboard_read",
    "inspect_application",
    "read_file",
    "search_documents",
    "search_files",
    "search_memory",
}

class HybridLLMClient:
    """Keep routine/private work local and escalate complex turns when configured."""

    def __init__(
        self,
        settings: Settings,
        *,
        local: LLMClient,
        cloud: LLMClient | None = None,
    ) -> None:
        self._settings = settings
        self._local = local
        self._cloud = cloud
        self.last_provider = "local"
        self._local_health = True
        self._local_health_at = 0.0

    @property
    def cloud_configured(self) -> bool:
        return self._cloud is not None

    async def configure_cloud(self, cloud: LLMClient | None) -> None:
        """Çalışma anında Gemini istemcisini değiştirir; orkestratör referansı kalır."""
        previous = self._cloud
        self._cloud = cloud
        if previous is not None and previous is not cloud and hasattr(previous, "aclose"):
            await previous.aclose()

    async def aclose(self) -> None:
        clients = [self._local, *([self._cloud] if self._cloud is not None else [])]
        await asyncio.gather(
            *(client.aclose() for client in clients if hasattr(client, "aclose")),
            return_exceptions=True,
        )

    async def health(self) -> bool:
        if self._settings.llm_routing_mode == "gemini" and self._cloud is not None:
            return await self._cloud.health()
        if await self._local.health():
            return True
        return bool(self._cloud is not None and await self._cloud.health())

    async def list_models(self) -> list[str]:
        models = await self._local.list_models()
        if self._cloud is not None and self._settings.gemini_model not in models:
            models.append(self._settings.gemini_model)
        return models

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> CompletionResult:
        primary, secondary, provider = await self._select(messages)
        self.last_provider = provider
        try:
            return await primary.complete(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            )
        except LLMUnavailableError as primary_error:
            if secondary is None:
                raise
            fallback = "gemini" if provider == "local" else "local"
            logger.warning("llm_provider_fallback", primary=provider, fallback=fallback)
            self.last_provider = fallback
            try:
                return await secondary.complete(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    enable_thinking=enable_thinking,
                )
            except LLMUnavailableError as fallback_error:
                raise _both_providers_failed(
                    provider, primary_error, fallback, fallback_error
                ) from fallback_error

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> AsyncIterator[StreamDelta]:
        primary, secondary, provider = await self._select(messages)
        self.last_provider = provider
        emitted = False
        try:
            async for delta in primary.stream(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            ):
                emitted = emitted or delta.kind in {"content", "thinking", "tool_call"}
                yield delta
            return
        except LLMUnavailableError as exc:
            if secondary is None or emitted:
                raise
            primary_error = exc

        fallback = "gemini" if provider == "local" else "local"
        logger.warning("llm_provider_fallback", primary=provider, fallback=fallback)
        self.last_provider = fallback
        try:
            async for delta in secondary.stream(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            ):
                yield delta
        except LLMUnavailableError as fallback_error:
            raise _both_providers_failed(
                provider, primary_error, fallback, fallback_error
            ) from fallback_error

    async def _select(
        self, messages: Sequence[ChatMessage]
    ) -> tuple[LLMClient, LLMClient | None, str]:
        if self._cloud is None or self._settings.llm_routing_mode == "local":
            return self._local, None, "local"
        local_up = await self._local_is_up()
        if not local_up:
            logger.info("llm_skip_unhealthy_local")
            return self._cloud, None, "gemini"
        if self._settings.llm_routing_mode == "gemini":
            return self._cloud, self._local, "gemini"
        if self._should_escalate(messages):
            return self._cloud, self._local, "gemini"
        return self._local, self._cloud, "local"

    async def _local_is_up(self) -> bool:
        now = time.monotonic()
        if now - self._local_health_at < 8.0:
            return self._local_health
        try:
            self._local_health = bool(await self._local.health())
        except Exception:
            self._local_health = False
        self._local_health_at = now
        return self._local_health

    def _should_escalate(self, messages: Sequence[ChatMessage]) -> bool:
        if not self._settings.gemini_allow_private_context and _contains_private_context(messages):
            return False
        if any(message.role == "tool" and message.name == "web_research" for message in messages):
            return True
        user_text = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        return bool(_CLOUD_INTENT.search(user_text) or len(user_text) >= 500)

def _both_providers_failed(
    primary: str,
    primary_error: LLMUnavailableError,
    fallback: str,
    fallback_error: LLMUnavailableError,
) -> LLMUnavailableError:
    """İki sağlayıcı da düşünce yalnızca yedeğin hatasını göstermez."""
    names = {"local": "Yerel model", "gemini": "Bulut model"}
    logger.error(
        "llm_all_providers_failed",
        primary=primary,
        primary_error=primary_error.user_message,
        fallback=fallback,
        fallback_error=fallback_error.user_message,
    )
    return LLMUnavailableError(
        f"{names.get(primary, primary)} da {names.get(fallback, fallback)} yedeği de "
        "cevap üretemedi.",
        details={
            primary: primary_error.user_message,
            fallback: fallback_error.user_message,
        },
    )

def _contains_private_context(messages: Sequence[ChatMessage]) -> bool:
    for message in messages:
        if message.role == "system" and (
            "\nKALICI HAFIZA\n" in message.content
            or "\nBELGELERDEN İLGİLİ BÖLÜMLER\n" in message.content
        ):
            return True
        if message.role == "tool" and message.name in _PRIVATE_TOOLS:
            return True
    return False
