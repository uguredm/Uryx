"""Pytest fixture'ları.

Testler SQLite (aiosqlite) üzerinde çalışır; PostgreSQL, Qdrant, LLM, Whisper
ve Piper gerektirmez. Dış bağımlılıklar sahte (fake) implementasyonlarla
değiştirilir.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("URYX_LOCAL_TOKEN", "")
os.environ.setdefault("JARVIS_LOCAL_TOKEN", "")
os.environ.setdefault("MEMORY_AUTO_ENABLED", "false")
os.environ.setdefault("EMBEDDING_DIM", "16")
os.environ.setdefault("LOG_LEVEL", "ERROR")

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.db.session import Database
from app.services.llm.base import ChatMessage, CompletionResult, StreamDelta
from app.services.rag.embeddings import HashEmbeddingProvider
from app.services.rag.retriever import SignalReranker

class FakeLLM:
    """Deterministik sahte LLM istemcisi."""

    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []
        self.reply = "Merhaba! Size nasıl yardımcı olabilirim?"
        self.tool_calls: list[dict[str, Any]] = []
        self.completion_json: str | None = None
        self.healthy = True

        self.unavailable = False

        self.stream_scripts: list[list[StreamDelta]] | None = None
        self.stream_kwargs: list[dict[str, Any]] = []

    async def health(self) -> bool:
        """Sağlık durumu."""
        return self.healthy

    async def list_models(self) -> list[str]:
        """Yüklü modeller."""
        return ["fake-model"] if self.healthy else []

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> CompletionResult:
        """Akışsız cevap."""
        self.calls.append(list(messages))
        return CompletionResult(content=self.completion_json or self.reply)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> AsyncIterator[StreamDelta]:
        """Cevabı kelime kelime akıtır."""
        if self.unavailable:
            from app.core.errors import LLMUnavailableError

            raise LLMUnavailableError()

        self.calls.append(list(messages))
        self.stream_kwargs.append(
            {
                "enable_thinking": enable_thinking,
                "max_tokens": max_tokens,
                "tools": tools,
            }
        )
        if self.stream_scripts is not None:
            if not self.stream_scripts:
                raise AssertionError("beklenmeyen ek stream çağrısı")
            for delta in self.stream_scripts.pop(0):
                yield delta
            return

        pending = self.tool_calls

        self.tool_calls = []

        if pending:
            yield StreamDelta(kind="finish", finish_reason="tool_calls", tool_calls=pending)
            return

        for word in self.reply.split(" "):
            yield StreamDelta(kind="content", text=word + " ")
        yield StreamDelta(kind="finish", finish_reason="stop")

    async def aclose(self) -> None:
        """Kapatma (no-op)."""

class FakeHTTPService:
    """Kapalı dış servisleri temsil eden sahte istemci."""

    def __init__(self, available: bool = False) -> None:
        self.available = available

    async def health(self) -> bool:
        """Sağlık durumu."""
        return self.available

    async def status(self) -> Any:
        """Durum."""
        return {"available": self.available}

    async def voices(self) -> list[Any]:
        """Ses listesi."""
        return []

    async def synthesize(self, *_args: Any, **_kwargs: Any) -> bytes:
        """Sahte ses."""
        return b""

    async def reload(self, model: str) -> Any:
        """Sahte Whisper reload — konteyner yok."""
        from app.schemas.speech import STTStatus

        self.last_reload = model
        return STTStatus(available=True, model=model, device="cpu", language="tr")

    async def aclose(self) -> None:
        """Kapatma (no-op)."""

@pytest.fixture
def settings() -> Settings:
    """Test ayarları."""
    get_settings.cache_clear()
    return get_settings()

@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    """Bellek içi SQLite veritabanı."""
    db = Database(settings)
    await db.connect()
    await db.create_all()
    yield db
    await db.disconnect()

@pytest.fixture
def fake_llm() -> FakeLLM:
    """Sahte LLM."""
    return FakeLLM()

@pytest_asyncio.fixture
async def container(
    settings: Settings, database: Database, fake_llm: FakeLLM
) -> AsyncIterator[Container]:
    """Dış bağımlılıkları sahte olan DI konteyneri."""
    instance = Container.build(settings)

    instance.database = database
    instance.llm = fake_llm  # type: ignore[assignment]
    instance.stt = FakeHTTPService()  # type: ignore[assignment]
    instance.tts = FakeHTTPService()  # type: ignore[assignment]

    hash_provider = HashEmbeddingProvider(settings.embedding_dim)
    instance.embeddings._using_fallback = True  # type: ignore[attr-defined]
    instance.embeddings._fallback = hash_provider  # type: ignore[attr-defined]

    instance.vector_store.available = False

    from app.services.chat.orchestrator import ChatOrchestrator
    from app.services.memory.evaluator import MemoryEvaluator
    from app.services.memory.service import MemoryService
    from app.services.rag.service import RAGService
    from app.services.system.metrics import SystemService
    from app.services.tools.backend_tools import BackendToolset
    from app.services.tools.executor import ToolExecutor

    instance.rag = RAGService(
        settings,
        database,
        instance.vector_store,
        instance.embeddings,
        reranker=SignalReranker(),
    )
    evaluator = MemoryEvaluator(fake_llm, max_tokens=settings.memory_evaluator_max_tokens)
    instance.memory = MemoryService(
        settings, database, instance.vector_store, instance.embeddings, evaluator
    )
    instance.backend_tools = BackendToolset(instance.rag, instance.memory)
    instance.executor = ToolExecutor(
        settings, instance.registry, instance.host_bridge, instance.backend_tools, database
    )
    instance.system = SystemService(
        settings,
        database=database,
        vector_store=instance.vector_store,
        llm=fake_llm,  # type: ignore[arg-type]
        stt=instance.stt,  # type: ignore[arg-type]
        tts=instance.tts,  # type: ignore[arg-type]
        host_bridge=instance.host_bridge,
    )
    instance.orchestrator = ChatOrchestrator(
        settings,
        llm=fake_llm,
        database=database,
        memory=instance.memory,
        rag=instance.rag,
        registry=instance.registry,
        executor=instance.executor,
        tts=instance.tts,  # type: ignore[arg-type]
    )

    yield instance
    await instance.orchestrator.shutdown()

@pytest_asyncio.fixture
async def app(container: Container) -> AsyncIterator[Any]:
    """Lifespan'ı devre dışı bırakılmış FastAPI uygulaması."""
    from app.main import create_app

    application = create_app()

    application.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]
    application.state.container = container
    yield application

@asynccontextmanager
async def _noop_lifespan(app_instance: Any) -> AsyncIterator[None]:
    """Testlerde gerçek bağlantı kurmayan lifespan.

    ``TestClient`` uygulamayı yeniden başlattığında ``app.state`` sıfırlandığı
    için konteyner burada yeniden bağlanır.
    """
    if getattr(app_instance.state, "container", None) is None:
        raise RuntimeError("Test konteyneri app.state üzerinde tanımlı olmalı.")
    yield

@pytest_asyncio.fixture
async def client(app: Any) -> AsyncIterator[Any]:
    """ASGI transport üzerinden HTTP istemcisi."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

@pytest.fixture(autouse=True)
def _pin_ui_language_tr():
    """Mevcut pytest kopyası Türkçe; D25 üretim varsayılanı İngilizce."""
    from app.core.locale import reset_ui_language, set_ui_language

    token = set_ui_language("tr")
    yield
    reset_ui_language(token)
