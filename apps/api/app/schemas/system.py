"""Sistem durumu ve metrik şemaları."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.tools import HostBridgeSnapshot

ServiceState = Literal["up", "down", "starting", "unknown", "degraded"]

class ServiceStatus(BaseModel):
    """Tek bir servisin sağlık durumu."""

    name: str
    display_name: str
    state: ServiceState = "unknown"
    detail: str | None = None
    latency_ms: int | None = None
    container_status: str | None = None
    url: str | None = None

class GPUInfo(BaseModel):
    """GPU bilgisi (host köprüsünden veya NVML'den)."""

    name: str = "Bilinmiyor"
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    vram_percent: float = 0.0
    utilization_percent: float = 0.0
    temperature_c: float | None = None
    driver_version: str | None = None
    available: bool = False

class DiskInfo(BaseModel):
    """Disk kullanımı."""

    mount: str
    total_gb: float = 0.0
    used_gb: float = 0.0
    percent: float = 0.0

class SystemMetrics(BaseModel):
    """Anlık sistem metrikleri."""

    cpu_percent: float = 0.0
    cpu_cores: int = 0
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    ram_percent: float = 0.0
    gpu: GPUInfo = Field(default_factory=GPUInfo)
    disks: list[DiskInfo] = Field(default_factory=list)
    source: Literal["host", "container"] = "container"
    timestamp: datetime

class ModelStatus(BaseModel):
    """Yüklü LLM durumu."""

    loaded: bool = False
    model_id: str | None = None
    max_model_len: int | None = None
    detail: str | None = None

class SystemStatus(BaseModel):
    """Sistem durumu ekranının tam veri seti."""

    services: list[ServiceStatus] = Field(default_factory=list)
    metrics: SystemMetrics
    model: ModelStatus = Field(default_factory=ModelStatus)
    host_bridge_connected: bool = False
    host_bridge: HostBridgeSnapshot | None = None
    last_error: str | None = None
    timestamp: datetime

class WSSystemUpdate(BaseModel):
    """``/ws/system`` üzerinden yayınlanan olay."""

    type: Literal["system_update"] = "system_update"
    payload: SystemStatus

class HealthResponse(BaseModel):
    """``/health`` cevabı."""

    status: Literal["ok", "degraded"] = "ok"
    version: str
    services: dict[str, str] = Field(default_factory=dict)
    host_bridge: Literal["up", "degraded", "down"] = "down"
