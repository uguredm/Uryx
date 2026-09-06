"""Dependency Injection konteyneri.

Tüm uzun ömürlü bağımlılıklar burada bir kez kurulur ve ``app.state.container``
üzerinden dağıtılır. Testlerde bu konteyner sahte bileşenlerle kurulabilir.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.repositories.settings import SettingsRepository
from app.db.session import Database
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.llm.base import LLMClient
from app.services.llm.gemini_client import GeminiClient
from app.services.llm.hybrid_client import HybridLLMClient
from app.services.llm.providers import detect_cloud_provider
from app.services.llm.vllm_client import VLLMClient
from app.services.memory.evaluator import MemoryEvaluator
from app.services.memory.service import MemoryService
from app.services.rag.embeddings import SentenceTransformerProvider, create_embedding_provider
from app.services.rag.retriever import create_reranker
from app.services.rag.service import RAGService
from app.services.rag.vector_store import QdrantVectorStore
from app.services.stt.client import WhisperClient
from app.services.system.metrics import SystemService
from app.services.tools.backend_tools import BackendToolset
from app.services.tools.executor import ToolExecutor
from app.services.tools.host_bridge import HostBridge
from app.services.tools.registry import ToolRegistry
from app.services.tts.client import PiperTTSClient

logger = get_logger(__name__)

@dataclass
class Container:
    """Uygulamanın bağımlılık grafiği."""

    settings: Settings
    database: Database
    vector_store: QdrantVectorStore
    embeddings: SentenceTransformerProvider
    llm: LLMClient
    stt: WhisperClient
    tts: PiperTTSClient
    host_bridge: HostBridge
    registry: ToolRegistry
    backend_tools: BackendToolset
    executor: ToolExecutor
    memory: MemoryService
    rag: RAGService
    system: SystemService
    orchestrator: ChatOrchestrator
    env_gemini_api_key: str
    env_gemini_model: str
    env_gemini_enabled: bool
    env_gemini_url: str
    env_cloud_provider: str

    @classmethod
    def build(cls, settings: Settings) -> Container:
        """Bağımlılık grafiğini kurar (I/O yapmaz)."""
        database = Database(settings)
        vector_store = QdrantVectorStore(settings)
        embeddings = create_embedding_provider(settings)
        reranker = create_reranker(settings)
        local_llm = VLLMClient(settings)
        cloud_llm = (
            GeminiClient(settings)
            if settings.gemini_enabled and bool(settings.gemini_api_key.strip())
            else None
        )
        llm = HybridLLMClient(settings, local=local_llm, cloud=cloud_llm)
        stt = WhisperClient(settings)
        tts = PiperTTSClient(settings)
        host_bridge = HostBridge(default_timeout=settings.host_tool_timeout)
        registry = ToolRegistry()

        rag = RAGService(settings, database, vector_store, embeddings, reranker=reranker)

        evaluator = MemoryEvaluator(local_llm, max_tokens=settings.memory_evaluator_max_tokens)
        memory = MemoryService(settings, database, vector_store, embeddings, evaluator)

        backend_tools = BackendToolset(rag, memory)
        executor = ToolExecutor(settings, registry, host_bridge, backend_tools, database)

        system = SystemService(
            settings,
            database=database,
            vector_store=vector_store,
            llm=local_llm,
            stt=stt,
            tts=tts,
            host_bridge=host_bridge,
        )
        orchestrator = ChatOrchestrator(
            settings,
            llm=llm,
            database=database,
            memory=memory,
            rag=rag,
            registry=registry,
            executor=executor,
            tts=tts,
        )

        return cls(
            settings=settings,
            database=database,
            vector_store=vector_store,
            embeddings=embeddings,
            llm=llm,
            stt=stt,
            tts=tts,
            host_bridge=host_bridge,
            registry=registry,
            backend_tools=backend_tools,
            executor=executor,
            memory=memory,
            rag=rag,
            system=system,
            orchestrator=orchestrator,
            env_gemini_api_key=settings.gemini_api_key,
            env_gemini_model=settings.gemini_model,
            env_gemini_enabled=settings.gemini_enabled,
            env_gemini_url=settings.gemini_url,
            env_cloud_provider=settings.cloud_provider,
        )

    async def apply_ui_gemini(
        self,
        api_key: str,
        model: str | None,
        *,
        provider: str | None = None,
        url: str | None = None,
    ) -> None:
        """UI'dan gelen anahtarı ayarlara yazar ve bulut istemcisini yeniler."""
        self.settings.gemini_api_key = api_key
        if model:
            self.settings.gemini_model = model
        if provider:
            self.settings.cloud_provider = provider
        if url:
            self.settings.gemini_url = url
        self.settings.gemini_enabled = True
        await self.rebuild_gemini_client()

    async def apply_env_gemini(self) -> None:
        """UI anahtarı silinince ``.env`` değerlerine döner."""
        self.settings.gemini_api_key = self.env_gemini_api_key
        self.settings.gemini_model = self.env_gemini_model
        self.settings.gemini_enabled = self.env_gemini_enabled
        self.settings.gemini_url = self.env_gemini_url
        self.settings.cloud_provider = self.env_cloud_provider
        if self.env_gemini_api_key.strip() and self.env_gemini_enabled:
            resolved = detect_cloud_provider(self.env_gemini_api_key, self.env_gemini_model)
            self.settings.cloud_provider = resolved.id
            self.settings.gemini_url = resolved.url
        await self.rebuild_gemini_client()

    async def rebuild_gemini_client(self) -> None:
        """Hybrid istemcinin Gemini ayağını canlı değiştirir."""
        if not isinstance(self.llm, HybridLLMClient):
            return
        cloud = None
        if self.settings.gemini_enabled and self.settings.gemini_api_key.strip():
            cloud = GeminiClient(self.settings)
        await self.llm.configure_cloud(cloud)

    async def load_stored_gemini(self) -> None:
        """Veritabanındaki UI anahtarını süreç ayarlarına uygular."""
        if not self.database.available:
            return
        try:
            async with self.database.session() as session:
                value = await SettingsRepository(session).get("llm_credentials")
            api_key = str((value or {}).get("api_key") or "").strip()
            model = str((value or {}).get("model") or "").strip()
            provider = str((value or {}).get("provider") or "").strip()
            url = str((value or {}).get("url") or "").strip()
            if api_key:
                if not provider:
                    resolved = detect_cloud_provider(api_key, model)
                    provider, url = resolved.id, resolved.url
                await self.apply_ui_gemini(api_key, model or None, provider=provider, url=url)
        except Exception:
            logger.warning("llm_credentials_load_failed")

    async def startup(self) -> None:
        """Dış bağlantıları kurar. Hiçbir hata uygulamayı düşürmez."""
        await self.database.connect()
        await self.load_stored_gemini()

        await self.embeddings.load()
        load_reranker = getattr(self.rag, "load_reranker", None)
        if callable(load_reranker):
            await load_reranker()
        await self.vector_store.connect(dimension=self.embeddings.dimension)

        health = await asyncio.gather(
            self.llm.health(), self.stt.health(), self.tts.health(), return_exceptions=True
        )
        logger.info(
            "startup_health",
            database=self.database.available,
            qdrant=self.vector_store.available,
            vllm=_bool(health[0]),
            llm=_bool(health[0]),
            whisper=_bool(health[1]),
            tts=_bool(health[2]),
            embedding_model=self.embeddings.model_name,
        )

    async def shutdown(self) -> None:
        """Kaynakları serbest bırakır."""
        await self.orchestrator.shutdown()
        await asyncio.gather(
            self.llm.aclose(),
            self.stt.aclose(),
            self.tts.aclose(),
            self.vector_store.disconnect(),
            self.database.disconnect(),
            return_exceptions=True,
        )

def _bool(value: Any) -> bool:
    """Gather sonucunu güvenli biçimde bool'a çevirir."""
    return bool(value) if not isinstance(value, BaseException) else False
