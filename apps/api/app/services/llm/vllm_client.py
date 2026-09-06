"""OpenAI uyumlu LLM istemcisi (llama.cpp /v1, eski vLLM yolu).

Qwen ``<think>…</think>`` blokları akış sırasında ayrıştırılır ve ayrı bir
``thinking`` deltası olarak yayınlanır; düşünme modu kapalıyken tamamen atılır.
llama-server ``chat_template_kwargs.enable_thinking`` ve ``--jinja`` ile
araç çağrılarını destekler.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.core.logging import get_logger
from app.services.llm.base import ChatMessage, CompletionResult, StreamDelta

logger = get_logger(__name__)

THINK_TAGS = {"<think>": "</think>", "<thought>": "</thought>"}
CONTEXT_LIMIT_RE = re.compile(
    r"maximum context length is (\d+) tokens.*?requested (\d+) output tokens.*?"
    r"prompt contains at least (\d+) input tokens",
    re.IGNORECASE,
)

LLAMA_CONTEXT_RE = re.compile(
    r"(?:context (?:size|length|window).*?(?:exceed|overflow|full)|"
    r"n_ctx[^\d]*(\d+).*?(?:prompt|request)[^\d]*(\d+)|"
    r"requested tokens? \(.*?(\d+).*?\) exceed)",
    re.IGNORECASE,
)

class VLLMClient:
    """OpenAI ``/v1/chat/completions`` istemcisi (llama-server varsayılan)."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        provider_name: str = "LLM",
        vllm_extensions: bool = True,
        request_timeout: int | None = None,
    ) -> None:
        self._settings = settings
        self._model = model or settings.llm_model
        self._provider_name = provider_name
        self._vllm_extensions = vllm_extensions
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=(base_url or settings.vllm_url).rstrip("/"),
            timeout=httpx.Timeout(request_timeout or settings.llm_request_timeout, connect=10.0),
            headers={"Authorization": f"Bearer {api_key or settings.vllm_api_key}"},
        )
        self._model_cache: list[str] = []

    def _provider_http_error(self, status: int, detail: str) -> LLMUnavailableError:
        message = f"{self._provider_name} isteği başarısız oldu (HTTP {status})."
        if not self._vllm_extensions and status in {401, 403}:
            message += (
                " Anahtar bu sağlayıcıya ait değil olabilir. "
                "Cursor token’ı Gemini/OpenAI’de çalışmaz."
            )
        return LLMUnavailableError(message, details={"detail": detail})

    async def aclose(self) -> None:
        """İstemciyi kapatır."""
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> bool:
        """LLM sunucusu ayakta mı? (``GET /models``)."""
        try:
            response = await self._client.get("/models", timeout=5.0)
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def list_models(self) -> list[str]:
        """Yüklü model kimliklerini döndürür."""
        try:
            response = await self._client.get("/models", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            self._model_cache = [m["id"] for m in data.get("data", [])]
        except (httpx.HTTPError, OSError, KeyError, ValueError):
            return self._model_cache
        return self._model_cache

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        enable_thinking: bool,
        stream: bool,
    ) -> dict[str, Any]:
        """OpenAI uyumlu istek gövdesini kurar."""
        api_messages = [m.to_api() for m in messages]
        if not self._vllm_extensions:
            from app.core.locale import ui_language

            if ui_language() == "tr":
                language_guard = (
                    "ZORUNLU ÇIKTI KURALI: Görünür nihai yanıtın tamamı Türkçe olmalı. "
                    "İç düşünceyi, <think>/<thought> etiketlerini veya İngilizce analiz metnini "
                    "yanıta ekleme."
                )
            else:
                language_guard = (
                    "MANDATORY OUTPUT RULE: The entire visible final answer must be in English. "
                    "Do not append inner thoughts, <think>/<thought> tags, or analysis in another language."
                )
            if api_messages and api_messages[0].get("role") == "system":
                api_messages[0] = {
                    **api_messages[0],
                    "content": f"{language_guard}\n\n{api_messages[0].get('content', '')}",
                }
            else:
                api_messages.insert(0, {"role": "system", "content": language_guard})
        elif not enable_thinking:

            api_messages = _inject_no_think(api_messages)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens or self._settings.llm_max_tokens,
            "stream": stream,
        }
        if self._vllm_extensions:
            payload["temperature"] = (
                temperature if temperature is not None else self._settings.llm_temperature
            )
            payload["top_p"] = self._settings.llm_top_p

            payload["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}
        elif enable_thinking:
            payload["extra_body"] = {
                "google": {
                    "thinking_config": {
                        "thinking_level": "medium",
                        "include_thoughts": False,
                    }
                }
            }
        if stream and self._vllm_extensions:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools if self._vllm_extensions else _portable_tools(tools)
            payload["tool_choice"] = "auto"
        return payload

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
        _context_retried: bool = False,
    ) -> CompletionResult:
        """Tek seferlik cevap üretir."""
        payload = self._build_payload(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
            stream=False,
        )
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _safe_error_body(exc.response)
            retry_tokens = (
                None if _context_retried else _context_retry_tokens(detail, payload["max_tokens"])
            )
            if retry_tokens is not None:
                logger.warning(
                    "llm_context_retry",
                    requested=payload["max_tokens"],
                    reduced=retry_tokens,
                )
                return await self.complete(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=retry_tokens,
                    enable_thinking=enable_thinking,
                    _context_retried=True,
                )
            logger.error(
                "llm_http_error",
                provider=self._provider_name,
                status=exc.response.status_code,
                detail=detail,
            )
            raise self._provider_http_error(exc.response.status_code, detail) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise LLMUnavailableError() from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        raw_content = message.get("content") or ""
        thinking, content = split_thinking(raw_content)

        thinking = message.get("reasoning_content") or thinking

        return CompletionResult(
            content=content.strip(),
            thinking=(thinking or "").strip(),
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason") or "stop",
            usage=data.get("usage") or {},
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
        _context_retried: bool = False,
    ) -> AsyncIterator[StreamDelta]:
        """Cevabı SSE üzerinden parça parça üretir."""
        payload = self._build_payload(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
            stream=True,
        )
        parser = _ThinkingStreamParser(emit_thinking=enable_thinking)
        tool_accumulator: dict[int, dict[str, Any]] = {}

        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    retry_tokens = (
                        None
                        if _context_retried
                        else _context_retry_tokens(body, payload["max_tokens"])
                    )
                    if retry_tokens is not None:
                        logger.warning(
                            "llm_stream_context_retry",
                            requested=payload["max_tokens"],
                            reduced=retry_tokens,
                        )
                        async for retry_delta in self.stream(
                            messages,
                            tools=tools,
                            temperature=temperature,
                            max_tokens=retry_tokens,
                            enable_thinking=enable_thinking,
                            _context_retried=True,
                        ):
                            yield retry_delta
                        return
                    logger.error(
                        "llm_stream_error",
                        provider=self._provider_name,
                        status=response.status_code,
                        body=body,
                    )
                    raise self._provider_http_error(response.status_code, body)

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}

                    reasoning = delta.get("reasoning_content")
                    if reasoning and enable_thinking:
                        yield StreamDelta(kind="thinking", text=reasoning)

                    content_piece = delta.get("content")
                    if content_piece:
                        for emitted in parser.feed(content_piece):
                            yield emitted

                    for tc in delta.get("tool_calls") or []:
                        _accumulate_tool_call(tool_accumulator, tc)

                    finish = choice.get("finish_reason")
                    if finish:
                        for emitted in parser.flush():
                            yield emitted
                        yield StreamDelta(
                            kind="finish",
                            finish_reason=finish,
                            tool_calls=_finalize_tool_calls(tool_accumulator),
                        )
                        return
        except LLMUnavailableError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            logger.error("llm_stream_transport_error", provider=self._provider_name, error=str(exc))
            raise LLMUnavailableError() from exc

        for emitted in parser.flush():
            yield emitted
        yield StreamDelta(
            kind="finish",
            finish_reason="stop",
            tool_calls=_finalize_tool_calls(tool_accumulator),
        )

class _ThinkingStreamParser:
    """``<think>`` bloklarını akış içinde ayırır.

    Etiketler parça sınırlarına bölünebildiği için kısmi bir tampon tutulur.
    """

    def __init__(self, emit_thinking: bool) -> None:
        self._buffer = ""
        self._in_think = False
        self._close_tag = "</think>"
        self._emit_thinking = emit_thinking

    def feed(self, text: str) -> list[StreamDelta]:
        """Yeni parçayı işler ve yayınlanabilir deltaları döndürür."""
        self._buffer += text
        out: list[StreamDelta] = []

        while True:
            if self._in_think:
                idx = self._buffer.casefold().find(self._close_tag)
                if idx == -1:
                    safe = self._hold_back((self._close_tag,))
                    if safe and self._emit_thinking:
                        out.append(StreamDelta(kind="thinking", text=safe))
                    break
                piece, self._buffer = (
                    self._buffer[:idx],
                    self._buffer[idx + len(self._close_tag) :],
                )
                if piece and self._emit_thinking:
                    out.append(StreamDelta(kind="thinking", text=piece))
                self._in_think = False
            else:
                found = [
                    (self._buffer.casefold().find(open_tag), open_tag, close_tag)
                    for open_tag, close_tag in THINK_TAGS.items()
                ]
                found = [item for item in found if item[0] >= 0]
                idx, open_tag, close_tag = min(found, default=(-1, "", ""))
                if idx == -1:
                    safe = self._hold_back(tuple(THINK_TAGS))
                    if safe:
                        out.append(StreamDelta(kind="content", text=safe))
                    break
                piece, self._buffer = self._buffer[:idx], self._buffer[idx + len(open_tag) :]
                if piece:
                    out.append(StreamDelta(kind="content", text=piece))
                self._in_think = True
                self._close_tag = close_tag
        return out

    def _hold_back(self, tags: tuple[str, ...]) -> str:
        """Tamponun etiket başlangıcı olabilecek kuyruğunu saklı tutar."""
        keep = 0
        folded = self._buffer.casefold()
        for tag in tags:
            for size in range(min(len(tag) - 1, len(self._buffer)), 0, -1):
                if folded.endswith(tag[:size]):
                    keep = max(keep, size)
                    break
        if keep:
            safe, self._buffer = self._buffer[:-keep], self._buffer[-keep:]
        else:
            safe, self._buffer = self._buffer, ""
        return safe

    def flush(self) -> list[StreamDelta]:
        """Kalan tamponu boşaltır."""
        if not self._buffer:
            return []
        remaining, self._buffer = self._buffer, ""
        kind = "thinking" if self._in_think else "content"
        if kind == "thinking" and not self._emit_thinking:
            return []
        return [StreamDelta(kind=kind, text=remaining)]

def split_thinking(text: str) -> tuple[str, str]:
    """Tam metinden ``<think>`` bloğunu ayırır.

    Returns:
        ``(düşünme, içerik)`` çifti.
    """
    pattern = re.compile(r"<(think|thought)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
    thoughts = [match.group(2).strip() for match in pattern.finditer(text)]
    content = pattern.sub("", text)

    content = re.sub(r"<(?:think|thought)>.*$", "", content, flags=re.IGNORECASE | re.DOTALL)
    return "\n".join(thought for thought in thoughts if thought).strip(), content

def _inject_no_think(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Son kullanıcı mesajına ``/no_think`` ekler (yoksa); Qwen thinking kapalı tutar."""
    if not messages:
        return messages
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") != "user":
            continue
        content = out[i].get("content")
        if isinstance(content, str):
            if "/no_think" in content or "/think" in content:
                return out
            out[i] = {**out[i], "content": f"{content}\n/no_think"}
        return out
    return out

def _accumulate_tool_call(acc: dict[int, dict[str, Any]], delta: dict[str, Any]) -> None:
    """Parça parça gelen tool_call verisini birleştirir."""
    index = int(delta.get("index", 0))
    entry = acc.setdefault(
        index,
        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
    )
    if delta.get("id"):
        entry["id"] = delta["id"]
    fn = delta.get("function") or {}
    if fn.get("name"):
        entry["function"]["name"] = fn["name"]
    if fn.get("arguments"):
        entry["function"]["arguments"] += fn["arguments"]

def _finalize_tool_calls(acc: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Biriktirilmiş araç çağrılarını sıralı listeye çevirir."""
    return [acc[i] for i in sorted(acc) if acc[i]["function"]["name"]]

def _portable_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove OpenAI-only schema hints before using another compatible endpoint."""
    portable: list[dict[str, Any]] = []
    for tool in tools:
        function = dict(tool.get("function") or {})
        function.pop("strict", None)
        portable.append({**tool, "function": function})
    return portable

def _context_retry_tokens(error_body: str, current_max_tokens: int) -> int | None:
    """Returns a smaller output budget when the server reports a context overflow.

    vLLM-style messages report the prompt size as "at least" the remaining window.
    llama.cpp may use different wording; we fall back to halving max_tokens once.
    """
    match = CONTEXT_LIMIT_RE.search(error_body)
    if match:
        context_limit, _requested, input_tokens = (int(value) for value in match.groups())
        available = context_limit - input_tokens - 32
        if available < 128 or available >= current_max_tokens:
            return None
        return available
    if LLAMA_CONTEXT_RE.search(error_body) or (
        "context" in error_body.lower()
        and ("exceed" in error_body.lower() or "overflow" in error_body.lower())
    ):
        reduced = max(128, current_max_tokens // 2)
        return reduced if reduced < current_max_tokens else None
    return None

def _safe_error_body(response: httpx.Response) -> str:
    """Hata gövdesini güvenli biçimde metne çevirir."""
    try:
        return json.dumps(response.json(), ensure_ascii=False)[:500]
    except (ValueError, TypeError):
        return response.text[:500]
