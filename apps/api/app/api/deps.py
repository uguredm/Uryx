"""FastAPI bağımlılık sağlayıcıları.

Route'lar somut sınıfları değil bu sağlayıcıları kullanır; testlerde
``app.dependency_overrides`` ile kolayca değiştirilebilir.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, WebSocket

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.errors import DatabaseUnavailableError
from app.db.session import Database
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.memory.service import MemoryService
from app.services.rag.service import RAGService
from app.services.stt.client import WhisperClient
from app.services.system.metrics import SystemService
from app.services.tools.executor import ToolExecutor
from app.services.tools.host_bridge import HostBridge
from app.services.tools.registry import ToolRegistry
from app.services.tts.client import PiperTTSClient

def get_container(request: Request) -> Container:
    """İstek bağlamından DI konteynerini döndürür."""
    container: Container = request.app.state.container
    return container

def get_ws_container(websocket: WebSocket) -> Container:
    """WebSocket bağlamından DI konteynerini döndürür."""
    container: Container = websocket.app.state.container
    return container

ContainerDep = Annotated[Container, Depends(get_container)]
WSContainerDep = Annotated[Container, Depends(get_ws_container)]

def get_config() -> Settings:
    """Ayarları döndürür."""
    return get_settings()

def get_database(container: ContainerDep) -> Database:
    """Veritabanı sarmalayıcısı."""
    return container.database

def require_database(container: ContainerDep) -> Database:
    """Veritabanı zorunlu olan endpoint'ler için.

    Raises:
        DatabaseUnavailableError: PostgreSQL erişilemezse.
    """
    if not container.database.available:
        raise DatabaseUnavailableError()
    return container.database

def get_orchestrator(container: ContainerDep) -> ChatOrchestrator:
    """Sohbet orkestratörü."""
    return container.orchestrator

def get_memory_service(container: ContainerDep) -> MemoryService:
    """Hafıza servisi."""
    return container.memory

def get_rag_service(container: ContainerDep) -> RAGService:
    """RAG servisi."""
    return container.rag

def get_registry(container: ContainerDep) -> ToolRegistry:
    """Araç kayıt defteri."""
    return container.registry

def get_executor(container: ContainerDep) -> ToolExecutor:
    """Araç çalıştırıcı."""
    return container.executor

def get_host_bridge(container: ContainerDep) -> HostBridge:
    """Host köprüsü."""
    return container.host_bridge

def get_system_service(container: ContainerDep) -> SystemService:
    """Sistem servisi."""
    return container.system

def get_stt(container: ContainerDep) -> WhisperClient:
    """STT istemcisi."""
    return container.stt

def get_tts(container: ContainerDep) -> PiperTTSClient:
    """TTS istemcisi."""
    return container.tts

SettingsDep = Annotated[Settings, Depends(get_config)]
DatabaseDep = Annotated[Database, Depends(require_database)]
OrchestratorDep = Annotated[ChatOrchestrator, Depends(get_orchestrator)]
MemoryDep = Annotated[MemoryService, Depends(get_memory_service)]
RAGDep = Annotated[RAGService, Depends(get_rag_service)]
RegistryDep = Annotated[ToolRegistry, Depends(get_registry)]
ExecutorDep = Annotated[ToolExecutor, Depends(get_executor)]
HostBridgeDep = Annotated[HostBridge, Depends(get_host_bridge)]
SystemDep = Annotated[SystemService, Depends(get_system_service)]
STTDep = Annotated[WhisperClient, Depends(get_stt)]
TTSDep = Annotated[PiperTTSClient, Depends(get_tts)]
