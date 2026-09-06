"""LLM istemcisi arayüzü.

Servis katmanı somut LLM implementasyonuna değil bu protokole bağlıdır; bu
sayede testlerde sahte istemci enjekte edilebilir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

@dataclass(slots=True)
class ChatMessage:
    """LLM'e gönderilen tek mesaj."""

    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_api(self) -> dict[str, Any]:
        """OpenAI uyumlu sözlüğe dönüştürür."""
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload

@dataclass(slots=True)
class StreamDelta:
    """Akıştan gelen tek bir parça."""

    kind: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None

@dataclass(slots=True)
class CompletionResult:
    """Akışsız tamamlama sonucu."""

    content: str
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)

@runtime_checkable
class LLMClient(Protocol):
    """LLM istemcisi sözleşmesi."""

    async def aclose(self) -> None:
        """İstemci kaynaklarını kapatır."""
        ...

    async def health(self) -> bool:
        """Servis ayakta mı?"""
        ...

    async def list_models(self) -> list[str]:
        """Yüklü model kimlikleri."""
        ...

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> CompletionResult:
        """Tek seferlik cevap üretir."""
        ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> AsyncIterator[StreamDelta]:
        """Cevabı parça parça üretir."""
        ...
