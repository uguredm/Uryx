"""LangGraph paralel küme + OpenHands host retry birim testleri."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.errors import HostBridgeUnavailableError
from app.schemas.chat import ChatOptions
from app.schemas.tools import ToolResult
from app.services.llm.base import StreamDelta
from app.services.tools.policy import LAST_TOOL_ROUND_HINT, MAX_TRANSIENT_RETRIES

def _call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    import json

    return {
        "id": call_id,
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }

class TestParallelBatch:
    """Salt-okunur küme paralel; confirm/HIGH sırada."""

    def test_iki_arama_paralel_guvenli(self, container) -> None:
        calls = [
            _call("search_documents", {"query": "a"}, "c1"),
            _call("search_memory", {"query": "b"}, "c2"),
        ]
        assert container.orchestrator._batch_parallel_safe(
            calls,
            confirmation_enabled=True,
            conversation_id="conv-p",
            executed=[],
        )

    def test_high_kume_sirali_kalir(self, container) -> None:
        calls = [
            _call("search_documents", {"query": "a"}, "c1"),
            _call("delete_file", {"path": "C:/a.txt"}, "c2"),
        ]
        assert not container.orchestrator._batch_parallel_safe(
            calls,
            confirmation_enabled=True,
            conversation_id="conv-p",
            executed=[],
        )

    def test_medium_onay_sirali_kalir(self, container) -> None:
        calls = [
            _call("search_documents", {"query": "a"}, "c1"),
            _call("open_application", {"name": "notepad"}, "c2"),
        ]
        assert not container.orchestrator._batch_parallel_safe(
            calls,
            confirmation_enabled=True,
            conversation_id="conv-p",
            executed=[],
        )

    async def test_paralel_calisma_ortusur(self, container) -> None:
        started: list[float] = []
        original = container.executor.execute

        async def slow_execute(*args: Any, **kwargs: Any) -> ToolResult:
            started.append(time.monotonic())
            await asyncio.sleep(0.06)
            return await original(*args, **kwargs)

        container.executor.execute = slow_execute  # type: ignore[method-assign]
        calls = [
            _call("search_documents", {"query": "a"}, "c1"),
            _call("search_memory", {"query": "b"}, "c2"),
        ]
        events: list[Any] = []

        async def emit(event: Any) -> None:
            events.append(event)

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-p",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert len(out) == 2
        assert len(started) == 2
        assert abs(started[0] - started[1]) < 0.05
        assert any(getattr(e, "type", None) == "tool_call" for e in events)

    async def test_paralel_beklenmeyen_hata_kardesi_korur(self, container) -> None:
        original = container.executor.execute

        async def boom(tool_name: str, *args: Any, **kwargs: Any) -> ToolResult:
            if tool_name == "search_documents":
                raise RuntimeError("patladi")
            return await original(tool_name, *args, **kwargs)

        container.executor.execute = boom  # type: ignore[method-assign]
        calls = [
            _call("search_documents", {"query": "a"}, "c1"),
            _call("search_memory", {"query": "b"}, "c2"),
        ]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-p",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert len(out) == 2
        crashed = next(m for m in out if m.name == "search_documents")
        assert "patladi" in crashed.content
        sibling = next(m for m in out if m.name == "search_memory")
        assert "patladi" not in sibling.content

class TestBackendRetry:
    """OpenHands extras: web_search tükenince LLM gözleminde retries+hint."""

    async def test_web_search_tukenen_gozlem_llm_extras(self, container) -> None:
        hits = {"n": 0}

        async def always_down(*_a: Any, **_k: Any) -> list[Any]:
            hits["n"] += 1
            raise ConnectionError("kopuk")

        container.backend_tools._web_search.search = always_down  # type: ignore[method-assign]
        result = await container.executor.execute("web_search", {"query": "x"})
        assert result.success is False
        assert hits["n"] == MAX_TRANSIENT_RETRIES
        assert result.retries == MAX_TRANSIENT_RETRIES
        assert "3/3" in (result.error or "")
        llm = result.to_llm_content()
        assert '"retries": 3' in llm
        assert "tekrarlama" in llm

class TestHostRetry:
    """Kopuşta 3 deneme; HIGH timeout tekrarlanmaz."""

    async def test_kopusta_uc_deneme_sonra_mesaj(self, container) -> None:
        hits = {"n": 0}

        async def always_down(*_a: Any, **_k: Any) -> dict[str, Any]:
            hits["n"] += 1
            raise HostBridgeUnavailableError(
                "Masaüstü uygulaması bağlı değil.",
                details={"retryable": True, "reason": "disconnected"},
            )

        container.executor._host.call = always_down  # type: ignore[method-assign]
        result = await container.executor.execute("get_cpu_usage", {})
        assert result.success is False
        assert hits["n"] == MAX_TRANSIENT_RETRIES
        assert result.retries == MAX_TRANSIENT_RETRIES
        assert "yeniden deneme" in (result.error or "")
        llm = result.to_llm_content()
        assert '"retries": 3' in llm
        assert "tekrarlama" in llm

    async def test_ikinci_denemede_toparlanir(self, container) -> None:
        hits = {"n": 0}

        async def flaky(*_a: Any, **_k: Any) -> dict[str, Any]:
            hits["n"] += 1
            if hits["n"] < 2:
                raise HostBridgeUnavailableError(
                    details={"retryable": True, "reason": "send_failed"}
                )
            return {"success": True, "result": {"ok": True}}

        container.executor._host.call = flaky  # type: ignore[method-assign]
        result = await container.executor.execute("get_cpu_usage", {})
        assert result.success is True
        assert result.result["ok"] is True
        assert hits["n"] == 2

    async def test_high_timeout_tekrarlanmaz(self, container) -> None:
        hits = {"n": 0}

        async def timeout(*_a: Any, **_k: Any) -> dict[str, Any]:
            hits["n"] += 1
            raise HostBridgeUnavailableError(
                "cevap vermedi",
                details={"retryable": False, "reason": "timeout"},
            )

        container.executor._host.call = timeout  # type: ignore[method-assign]
        prepared = container.executor.prepare("delete_file", {"path": "C:/tmp/a.txt"})
        result = await container.executor.execute(
            "delete_file",
            {"path": "C:/tmp/a.txt"},
            confirmation_ticket=prepared.confirmation_ticket,
        )
        assert result.success is False
        assert hits["n"] == 1

class TestInvalidToolJson:
    """Bozuk / kesik argüman çalıştırılmaz; LLM gözlem alır."""

    async def test_kesik_json_arac_calismaz(self, container) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        calls = [
            {
                "id": "c1",
                "function": {"name": "search_documents", "arguments": '{"query": "kesik'},
            }
        ]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-json",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert hits["n"] == 0
        assert len(out) == 1
        assert "unparseable JSON" in out[0].content
        assert "recoverable" in out[0].content
        assert "nudge" not in out[0].content

    async def test_ikinci_ayni_hata_nudge(self, container) -> None:
        executed: list[dict[str, Any]] = [
            {"tool_name": "search_documents", "success": False, "invalid": True}
        ]
        calls = [
            {
                "id": "c2",
                "function": {"name": "search_documents", "arguments": '{"query": "kesik'},
            }
        ]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-nudge",
            emit=emit,
            confirm=None,
            executed=executed,
            confirmation_enabled=True,
        )
        assert len(out) == 1
        assert '"nudge": true' in out[0].content
        assert "keser" in out[0].content

class TestUnknownToolName:
    """Agno: hayalet araç çalışmaz; available + did_you_mean LLM JSON'a gider."""

    async def test_bilinmeyen_arac_liste_ve_oneri(self, container) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        calls = [_call("search_documnts", {"query": "uryx"}, "c-ghost")]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-ghost",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert hits["n"] == 0
        assert len(out) == 1
        assert "search_documents" in out[0].content
        assert "did_you_mean" in out[0].content
        assert "available" in out[0].content
        assert "recoverable" in out[0].content

class TestDuplicateBatch:
    """Trae: aynı turda kopya çağrı çalıştırılmaz."""

    async def test_ayni_cagri_bir_kez_calisir(self, container) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        calls = [
            _call("search_documents", {"query": "uryx"}, "c1"),
            _call("search_documents", {"query": "uryx"}, "c2"),
        ]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-dup",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert hits["n"] == 1
        assert len(out) == 1

class TestSchemaRetry:
    """PydanticAI: eksik zorunlu alan çalışmaz; required LLM JSON'a gider."""

    async def test_eksik_zorunlu_alan_retry(self, container) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        calls = [_call("open_application", {}, "c-schema")]

        async def emit(_event: Any) -> None:
            return None

        out = await container.orchestrator._run_tool_calls(
            calls,
            conversation_id="conv-schema",
            emit=emit,
            confirm=None,
            executed=[],
            confirmation_enabled=True,
        )
        assert hits["n"] == 0
        assert len(out) == 1
        assert '"required"' in out[0].content
        assert "name" in out[0].content
        assert '"retry": true' in out[0].content

class TestLastRoundWrapUp:
    """AutoGPT: son turda tools=None + sistem ipucu; yeni araç çalışmaz."""

    async def test_son_tur_sema_yok_ozet_yazar(self, container, fake_llm, monkeypatch) -> None:
        import app.services.chat.orchestrator as orch

        monkeypatch.setattr(orch, "MAX_TOOL_ROUNDS", 2)
        execute_hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            execute_hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        fake_llm.stream_scripts = [
            [
                StreamDelta(
                    kind="finish",
                    finish_reason="tool_calls",
                    tool_calls=[
                        _call("search_documents", {"query": "x"}, "c-wrap"),
                    ],
                )
            ],
            [
                StreamDelta(kind="content", text="Belgelerde x yok; özet bu."),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
        ]

        async def emit(_event: Any) -> None:
            return None

        result = await container.orchestrator.run_turn(
            conversation_id=None,
            user_message="Ne var ne yok?",
            options=ChatOptions(use_rag=False, use_memory=False, use_tools=True),
            emit=emit,
        )
        assert execute_hits["n"] == 1
        assert fake_llm.stream_kwargs[0]["tools"]
        assert fake_llm.stream_kwargs[1]["tools"] is None
        last_msgs = fake_llm.calls[1]
        assert any(
            getattr(m, "role", None) == "system" and LAST_TOOL_ROUND_HINT in getattr(m, "content", "")
            for m in last_msgs
        )
        assert "özet" in result["content"]

class TestTextToolCallFallback:
    """Qwen-Agent: native tool_calls boşken metin <tool_call> çalışır."""

    async def test_metin_arac_calisir(self, container, fake_llm) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        blob = (
            '<tool_call>{"name": "search_documents", '
            '"arguments": {"query": "uryx"}}</tool_call>'
        )
        fake_llm.stream_scripts = [
            [
                StreamDelta(kind="content", text=blob),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
            [
                StreamDelta(kind="content", text="Arama bitti."),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
        ]

        async def emit(_event: Any) -> None:
            return None

        result = await container.orchestrator.run_turn(
            conversation_id=None,
            user_message="Uryx nedir?",
            options=ChatOptions(use_rag=False, use_memory=False, use_tools=True),
            emit=emit,
        )
        assert hits["n"] == 1
        assert "tool_call" not in result["content"]
        assert "Arama" in result["content"]

class TestReactToolCallFallback:
    """LlamaIndex: native boşken Action/Action Input çalışır."""

    async def test_react_arac_calisir(self, container, fake_llm) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        blob = (
            "Thought: ara\n"
            "Action: search_documents\n"
            'Action Input: {"query": "uryx"}\n'
        )
        fake_llm.stream_scripts = [
            [
                StreamDelta(kind="content", text=blob),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
            [
                StreamDelta(kind="content", text="ReAct bitti."),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
        ]

        async def emit(_event: Any) -> None:
            return None

        result = await container.orchestrator.run_turn(
            conversation_id=None,
            user_message="Uryx nedir?",
            options=ChatOptions(use_rag=False, use_memory=False, use_tools=True),
            emit=emit,
        )
        assert hits["n"] == 1
        assert "Action:" not in result["content"]
        assert "ReAct" in result["content"]

class TestPythonicToolCallFallback:
    """vLLM: native boşken [fn(kw=...)] çalışır."""

    async def test_pythonic_arac_calisir(self, container, fake_llm) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        blob = '[search_documents(query="uryx")]'
        fake_llm.stream_scripts = [
            [
                StreamDelta(kind="content", text=blob),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
            [
                StreamDelta(kind="content", text="Pythonic bitti."),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
        ]

        async def emit(_event: Any) -> None:
            return None

        result = await container.orchestrator.run_turn(
            conversation_id=None,
            user_message="Uryx nedir?",
            options=ChatOptions(use_rag=False, use_memory=False, use_tools=True),
            emit=emit,
        )
        assert hits["n"] == 1
        assert "search_documents" not in result["content"]
        assert "Pythonic" in result["content"]

class TestMistralToolCallFallback:
    """SGLang: native boşken [TOOL_CALLS] çalışır."""

    async def test_mistral_arac_calisir(self, container, fake_llm) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        blob = '[TOOL_CALLS] [{"name": "search_documents", "arguments": {"query": "uryx"}}]'
        fake_llm.stream_scripts = [
            [
                StreamDelta(kind="content", text=blob),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
            [
                StreamDelta(kind="content", text="Mistral bitti."),
                StreamDelta(kind="finish", finish_reason="stop"),
            ],
        ]

        async def emit(_event: Any) -> None:
            return None

        result = await container.orchestrator.run_turn(
            conversation_id=None,
            user_message="Uryx nedir?",
            options=ChatOptions(use_rag=False, use_memory=False, use_tools=True),
            emit=emit,
        )
        assert hits["n"] == 1
        assert "TOOL_CALLS" not in result["content"]
        assert "Mistral" in result["content"]

class TestIdempotentCacheHit:
    """CrewAI: ikinci turda aynı salt-okunur çağrı çalışmaz."""

    async def test_ikinci_ayni_arama_onbellek(self, container) -> None:
        hits = {"n": 0}
        original = container.executor.execute

        async def spy(*args: Any, **kwargs: Any) -> ToolResult:
            hits["n"] += 1
            return await original(*args, **kwargs)

        container.executor.execute = spy  # type: ignore[method-assign]
        executed: list[dict[str, Any]] = []

        async def emit(_event: Any) -> None:
            return None

        first = await container.orchestrator._run_tool_calls(
            [_call("search_documents", {"query": "uryx"}, "c1")],
            conversation_id="conv-cache",
            emit=emit,
            confirm=None,
            executed=executed,
            confirmation_enabled=True,
        )
        second = await container.orchestrator._run_tool_calls(
            [_call("search_documents", {"query": "uryx"}, "c2")],
            conversation_id="conv-cache",
            emit=emit,
            confirm=None,
            executed=executed,
            confirmation_enabled=True,
        )
        assert hits["n"] == 1
        assert len(first) == 1
        assert len(second) == 1
        assert '"cached": true' in second[0].content
