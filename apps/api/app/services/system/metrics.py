"""Sistem metrikleri ve servis sağlığı toplayıcısı.

Metrik kaynağı önceliği:

1. **Host** — Electron masaüstü uygulaması bağlıysa gerçek Windows metrikleri
   (GPU dahil) host köprüsünden gelir.
2. **Container** — masaüstü bağlı değilse ``psutil`` ile container metrikleri
   raporlanır ve ``source="container"`` olarak işaretlenir.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.locale import loc, ui_language
from app.core.logging import get_logger
from app.db.session import Database
from app.schemas.system import (
    DiskInfo,
    GPUInfo,
    ModelStatus,
    ServiceStatus,
    SystemMetrics,
    SystemStatus,
)
from app.schemas.tools import HostBridgeSnapshot
from app.services.llm.base import LLMClient
from app.services.rag.vector_store import QdrantVectorStore
from app.services.stt.client import WhisperClient
from app.services.tools.host_bridge import HostBridge
from app.services.tts.client import PiperTTSClient

logger = get_logger(__name__)

class SystemService:
    """Sistem durumu ekranını besleyen servis."""

    def __init__(
        self,
        settings: Settings,
        *,
        database: Database,
        vector_store: QdrantVectorStore,
        llm: LLMClient,
        stt: WhisperClient,
        tts: PiperTTSClient,
        host_bridge: HostBridge,
    ) -> None:
        self._settings = settings
        self._db = database
        self._vectors = vector_store
        self._llm = llm
        self._stt = stt
        self._tts = tts
        self._host = host_bridge
        self._last_error: str | None = None
        self._service_cache: tuple[float, str, list[ServiceStatus]] | None = None
        self._model_cache: tuple[float, str, ModelStatus] | None = None

    async def metrics(self) -> SystemMetrics:
        """Anlık sistem metriklerini döndürür."""
        host_metrics = self._host.last_metrics
        if self._host.connected and host_metrics:
            return _metrics_from_host(host_metrics)
        return await asyncio.to_thread(_container_metrics)

    async def services(self, *, use_cache: bool = True) -> list[ServiceStatus]:
        """Tüm servislerin sağlık durumunu döndürür."""
        now = time.monotonic()
        lang = ui_language()
        if (
            use_cache
            and self._service_cache
            and now - self._service_cache[0] < self._settings.docker_health_interval
            and self._service_cache[1] == lang
        ):
            return self._service_cache[2]

        results = await asyncio.gather(
            self._check_database(),
            self._check_qdrant(),
            self._check_llm(),
            self._check_whisper(),
            self._check_tts(),
            return_exceptions=True,
        )

        statuses: list[ServiceStatus] = []
        for item in results:
            if isinstance(item, ServiceStatus):
                statuses.append(item)
            elif isinstance(item, BaseException):  # pragma: no cover
                logger.warning("health_check_error", error=str(item))

        statuses.append(
            ServiceStatus(
                name="uryx-api",
                display_name="Uryx API",
                state="up",
                detail=loc("Çalışıyor", "Running"),
            )
        )
        snap = self._host.snapshot()
        statuses.append(
            ServiceStatus(
                name="desktop",
                display_name=loc("Masaüstü köprüsü", "Desktop bridge"),
                state=snap["state"],
                detail=_desktop_detail(snap),
            )
        )

        await self._attach_container_status(statuses)
        self._service_cache = (now, lang, statuses)
        return statuses

    async def _check_database(self) -> ServiceStatus:
        """PostgreSQL sağlığı."""
        started = time.perf_counter()
        ok = await self._db.ping()
        return ServiceStatus(
            name="postgres",
            display_name="PostgreSQL",
            state="up" if ok else "down",
            detail=None if ok else (self._db.last_error or loc("Bağlantı kurulamadı", "Connection failed"))[:200],
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _check_qdrant(self) -> ServiceStatus:
        """Qdrant sağlığı."""
        started = time.perf_counter()
        ok = await self._vectors.ping()
        return ServiceStatus(
            name="qdrant",
            display_name="Qdrant",
            state="up" if ok else "down",
            detail=None if ok else (self._vectors.last_error or loc("Bağlantı kurulamadı", "Connection failed"))[:200],
            latency_ms=int((time.perf_counter() - started) * 1000),
            url=self._settings.qdrant_url,
        )

    async def _check_llm(self) -> ServiceStatus:
        """llama.cpp (OpenAI /v1) sağlığı."""
        started = time.perf_counter()
        ok = await self._llm.health()
        return ServiceStatus(
            name="llm",
            display_name="LLM (llama.cpp)",
            state="up" if ok else "down",
            detail=None if ok else loc(
                "Model yükleniyor olabilir veya GGUF/servis kapalı",
                "The model may be loading, or the GGUF/service is down",
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
            url=self._settings.vllm_url,
        )

    async def _check_whisper(self) -> ServiceStatus:
        """Whisper sağlığı."""
        started = time.perf_counter()
        ok = await self._stt.health()
        return ServiceStatus(
            name="whisper",
            display_name="Whisper (STT)",
            state="up" if ok else "down",
            detail=None if ok else loc("Konuşma tanıma kullanılamıyor", "Speech recognition is unavailable"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            url=self._settings.whisper_url,
        )

    async def _check_tts(self) -> ServiceStatus:
        """TTS sağlığı."""
        started = time.perf_counter()
        ok = await self._tts.health()
        return ServiceStatus(
            name="tts",
            display_name="Piper (TTS)",
            state="up" if ok else "down",
            detail=None if ok else loc("Seslendirme kullanılamıyor", "Speech output is unavailable"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            url=self._settings.tts_url,
        )

    async def _attach_container_status(self, statuses: list[ServiceStatus]) -> None:
        """Docker konteyner durumlarını sağlık listesine iliştirir."""
        try:
            containers = await asyncio.to_thread(_docker_container_states)
        except Exception:
            return
        mapping = {
            "postgres": "uryx-postgres",
            "qdrant": "uryx-qdrant",
            "llm": "uryx-llm",
            "whisper": "uryx-whisper",
            "tts": "uryx-tts",
            "uryx-api": "uryx-api",
        }
        for status in statuses:
            container_name = mapping.get(status.name)
            if container_name and container_name in containers:
                status.container_status = containers[container_name]
                if status.state == "down" and containers[container_name] == "starting":
                    status.state = "starting"
                    status.detail = loc("Konteyner başlatılıyor…", "Container is starting…")

    async def model_status(self) -> ModelStatus:
        """Yüklü LLM durumunu döndürür."""
        now = time.monotonic()
        lang = ui_language()
        if self._model_cache and now - self._model_cache[0] < 15 and self._model_cache[1] == lang:
            return self._model_cache[2]

        models = await self._llm.list_models()
        status = ModelStatus(
            loaded=bool(models),
            model_id=models[0] if models else self._settings.llm_model,
            max_model_len=self._settings.llm_max_model_len,
            detail=None
            if models
            else loc(
                "llama-server'da yüklü model bulunamadı (GGUF / LLM_MODEL).",
                "No model is loaded in llama-server (GGUF / LLM_MODEL).",
            ),
        )
        self._model_cache = (now, lang, status)
        return status

    async def status(self, *, use_cache: bool = True) -> SystemStatus:
        """Sistem durumu ekranının tam veri setini üretir."""
        services, metrics, model = await asyncio.gather(
            self.services(use_cache=use_cache),
            self.metrics(),
            self.model_status(),
        )
        snap = self._host.snapshot()
        down = [s.display_name for s in services if s.state == "down" and s.name != "desktop"]
        return SystemStatus(
            services=services,
            metrics=metrics,
            model=model,
            host_bridge_connected=self._host.connected,
            host_bridge=HostBridgeSnapshot.model_validate(snap),
            last_error=(
                self._last_error or (
                    loc("Çalışmayan servisler: ", "Services down: ") + ", ".join(down) if down else None
                )
            ),
            timestamp=datetime.now(UTC),
        )

    def set_last_error(self, message: str | None) -> None:
        """Arayüzde gösterilecek son hatayı ayarlar."""
        self._last_error = message[:500] if message else None

def _desktop_detail(snap: dict[str, Any]) -> str:
    """Masaüstü köprüsü sağlık açıklaması."""
    client = snap.get("client") if isinstance(snap.get("client"), dict) else {}
    version = str(client.get("version") or snap.get("version") or "").strip()
    tools = snap.get("tools") if isinstance(snap.get("tools"), list) else []
    if snap.get("state") == "up":
        parts = [loc("Electron uygulaması bağlı", "Electron app connected")]
        if version:
            parts.append(loc(f"sürüm {version}", f"version {version}"))
        if tools:
            parts.append(loc(f"{len(tools)} host aracı", f"{len(tools)} host tools"))
        return " · ".join(parts)
    if snap.get("circuit_open"):
        return loc(
            "Köprü bağlı görünüyor ama RPC ardışık hatalarla durduruldu",
            "The bridge looks connected but RPC stopped after repeated errors",
        )
    if snap.get("state") == "degraded":
        return loc(
            "Köprü bağlı ama metrik/yanıt gecikmeli (degraded)",
            "The bridge is connected but metrics/responses are delayed (degraded)",
        )
    return loc(
        "Masaüstü uygulaması bağlı değil (host araçları devre dışı)",
        "Desktop app is not connected (host tools disabled)",
    )

def _container_metrics() -> SystemMetrics:
    """psutil ile container içi metrikler."""
    import psutil

    memory = psutil.virtual_memory()
    disks: list[DiskInfo] = []
    for partition in psutil.disk_partitions(all=False)[:5]:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append(
            DiskInfo(
                mount=partition.mountpoint,
                total_gb=round(usage.total / 1e9, 1),
                used_gb=round(usage.used / 1e9, 1),
                percent=round(usage.percent, 1),
            )
        )

    return SystemMetrics(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        cpu_cores=psutil.cpu_count(logical=True) or 0,
        ram_total_mb=int(memory.total / 1024 / 1024),
        ram_used_mb=int(memory.used / 1024 / 1024),
        ram_percent=round(memory.percent, 1),
        gpu=GPUInfo(
            available=False,
            name=loc(
                "GPU bilgisi yalnızca masaüstü uygulaması bağlıyken okunabilir",
                "GPU info is available only while the desktop app is connected",
            ),
        ),
        disks=disks,
        source="container",
        timestamp=datetime.now(UTC),
    )

def _metrics_from_host(payload: dict[str, Any]) -> SystemMetrics:
    """Host köprüsünden gelen ham metrikleri şemaya çevirir."""
    gpu_payload = payload.get("gpu") or {}
    return SystemMetrics(
        cpu_percent=float(payload.get("cpu_percent", 0.0)),
        cpu_cores=int(payload.get("cpu_cores", 0)),
        ram_total_mb=int(payload.get("ram_total_mb", 0)),
        ram_used_mb=int(payload.get("ram_used_mb", 0)),
        ram_percent=float(payload.get("ram_percent", 0.0)),
        gpu=GPUInfo(
            name=str(gpu_payload.get("name") or loc("Bilinmiyor", "Unknown")),
            vram_total_mb=int(gpu_payload.get("vram_total_mb", 0)),
            vram_used_mb=int(gpu_payload.get("vram_used_mb", 0)),
            vram_percent=float(gpu_payload.get("vram_percent", 0.0)),
            utilization_percent=float(gpu_payload.get("utilization_percent", 0.0)),
            temperature_c=(
                float(gpu_payload["temperature_c"])
                if gpu_payload.get("temperature_c") is not None
                else None
            ),
            driver_version=gpu_payload.get("driver_version"),
            available=bool(gpu_payload.get("available", False)),
        ),
        disks=[
            DiskInfo(
                mount=str(d.get("mount", "")),
                total_gb=float(d.get("total_gb", 0.0)),
                used_gb=float(d.get("used_gb", 0.0)),
                percent=float(d.get("percent", 0.0)),
            )
            for d in (payload.get("disks") or [])
        ],
        source="host",
        timestamp=datetime.now(UTC),
    )

def _docker_container_states() -> dict[str, str]:
    """Docker konteynerlerinin durumlarını okur."""
    import docker

    client = docker.from_env()
    states: dict[str, str] = {}
    for container in client.containers.list(all=True):
        health = (container.attrs.get("State", {}).get("Health", {}) or {}).get("Status")
        if health == "healthy":
            states[container.name] = "running"
        elif health == "starting":
            states[container.name] = "starting"
        else:
            states[container.name] = container.status
    return states
