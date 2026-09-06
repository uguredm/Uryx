"""vLLM request recovery tests."""

from __future__ import annotations

import json

import httpx
import pytest
from app.services.llm.base import ChatMessage
from app.services.llm.gemini_client import GeminiClient
from app.services.llm.vllm_client import VLLMClient, split_thinking

@pytest.mark.asyncio
async def test_stream_retries_with_smaller_output_budget_on_context_overflow(settings) -> None:
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads((await request.aread()).decode("utf-8")))
        if len(payloads) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": (
                            "This model's maximum context length is 8192 tokens. However, "
                            "you requested 2048 output tokens and your prompt contains at least "
                            "6145 input tokens."
                        )
                    }
                },
            )
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"content":"Tamam."},'
                '"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://vllm.test/v1",
    )
    client = VLLMClient(settings, client=http_client)
    try:
        deltas = [
            delta
            async for delta in client.stream(
                [ChatMessage(role="user", content="Test")],
                max_tokens=2048,
            )
        ]
    finally:
        await http_client.aclose()

    assert [payload["max_tokens"] for payload in payloads] == [2048, 2015]
    assert "".join(delta.text for delta in deltas if delta.kind == "content") == "Tamam."
    assert deltas[-1].finish_reason == "stop"

@pytest.mark.asyncio
async def test_gemini_openai_payload_uses_portable_tool_schema(settings) -> None:
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads((await request.aread()).decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "Tamam."},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.test/v1beta/openai",
    )
    gemini_settings = settings.model_copy(
        update={"gemini_api_key": "test", "gemini_model": "gemini-3.6-flash"}
    )
    client = GeminiClient(gemini_settings, client=http_client)
    try:
        await client.complete(
            [ChatMessage(role="user", content="Test")],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "example",
                        "description": "Example",
                        "strict": True,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            enable_thinking=True,
        )
    finally:
        await http_client.aclose()

    payload = payloads[0]
    assert payload["model"] == "gemini-3.6-flash"
    assert "chat_template_kwargs" not in payload
    assert "temperature" not in payload
    tools = payload["tools"]
    assert isinstance(tools, list)
    assert "strict" not in tools[0]["function"]
    assert payload["extra_body"]["google"]["thinking_config"]["include_thoughts"] is False
    assert "tamamı Türkçe" in payload["messages"][0]["content"]

def test_no_think_injected_when_thinking_disabled(settings) -> None:
    client = VLLMClient(settings, client=httpx.AsyncClient(base_url="http://llm.test/v1"))
    payload = client._build_payload(
        [ChatMessage(role="user", content="Merhaba")],
        tools=None,
        temperature=None,
        max_tokens=64,
        enable_thinking=False,
        stream=False,
    )
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["messages"][-1]["content"].endswith("/no_think")

def test_gemini_thought_etiketi_gorunur_cevaptan_ayrilir() -> None:
    thinking, content = split_thinking(
        "<thought>Considering the user's intent.</thought>Coğrafi Bilgi Sistemleri için Python."
    )

    assert thinking == "Considering the user's intent."
    assert content == "Coğrafi Bilgi Sistemleri için Python."
