"""Sistem durumu ve ayar endpoint'leri."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import ContainerDep, SettingsDep, SystemDep
from app.core.security import get_allowed_roots, require_token
from app.schemas.common import OkResponse
from app.schemas.llm_credentials import (
    LlmCredentialsReveal,
    LlmCredentialsStatus,
    LlmCredentialsUpdate,
)
from app.schemas.system import ServiceStatus, SystemMetrics, SystemStatus
from app.services.llm.credentials import LlmCredentialsService

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_token)])

@router.get("/status", response_model=SystemStatus, summary="Tam sistem durumu")
async def system_status(system: SystemDep) -> SystemStatus:
    """Servis sağlıkları, metrikler ve model durumu."""
    return await system.status(use_cache=False)

@router.get("/metrics", response_model=SystemMetrics, summary="Anlık metrikler")
async def system_metrics(system: SystemDep) -> SystemMetrics:
    """CPU / RAM / GPU / disk metrikleri."""
    return await system.metrics()

@router.get("/services", response_model=list[ServiceStatus], summary="Servis sağlıkları")
async def system_services(system: SystemDep) -> list[ServiceStatus]:
    """Docker servislerinin sağlık durumları."""
    return await system.services(use_cache=False)

@router.get("/config", summary="Etkin yapılandırma")
async def effective_config(settings: SettingsDep, container: ContainerDep) -> dict[str, Any]:
    """Arayüzün gösterdiği (hassas olmayan) etkin ayarlar."""
    return {
        "app_version": settings.app_version,
        "llm": {
            "model": settings.llm_model,
            "max_model_len": settings.llm_max_model_len,
            "n_gpu_layers": settings.llm_n_gpu_layers,
            "gguf_file": settings.llm_gguf_file,
            "gpu_memory_utilization": settings.llm_gpu_memory_utilization,
            "max_num_seqs": settings.llm_max_num_seqs,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "url": settings.vllm_url,
            "routing_mode": settings.llm_routing_mode,
            "cloud_model": settings.gemini_model,
            "cloud_configured": bool(settings.gemini_enabled and settings.gemini_api_key.strip()),
            "cloud_provider": settings.cloud_provider,
            "private_context_allowed": settings.gemini_allow_private_context,
        },
        "embedding": {
            "model": container.embeddings.model_name,
            "dimension": container.embeddings.dimension,
            "device": settings.embedding_device,
            "fallback_active": container.embeddings.using_fallback,
        },
        "rag": {
            "chunk_size": settings.rag_chunk_size,
            "chunk_overlap": settings.rag_chunk_overlap,
            "top_k": settings.rag_top_k,
            "min_score": settings.rag_min_score,
            "max_file_mb": settings.rag_max_file_mb,
        },
        "memory": {
            "auto_enabled": settings.memory_auto_enabled,
            "top_k": settings.memory_top_k,
        },
        "stt": {
            "model": settings.whisper_model,
            "language": settings.whisper_language,
            "url": settings.whisper_url,
        },
        "tts": {
            "voice": settings.tts_voice,
            "speed": settings.tts_speed,
            "enabled": settings.tts_enabled,
            "url": settings.tts_url,
        },
        "wake_word": {
            "source": "desktop_store",
            "api_controls": False,
        },
        "security": {
            "auth_enabled": settings.auth_enabled,
            "require_tool_confirmation": settings.require_tool_confirmation,
            "allowed_paths": [str(p) for p in get_allowed_roots(settings)],
        },
        "metrics_interval": settings.system_metrics_interval,
    }

@router.get(
    "/llm-credentials",
    response_model=LlmCredentialsStatus,
    summary="Bulut LLM kimlik bilgisi özeti",
)
async def llm_credentials_status(container: ContainerDep) -> LlmCredentialsStatus:
    """Maskeli özet; ham anahtar içermez."""
    return LlmCredentialsStatus.model_validate(await LlmCredentialsService(container).status())

@router.put(
    "/llm-credentials",
    response_model=LlmCredentialsStatus,
    summary="Bulut LLM kimlik bilgisini kaydet",
)
async def llm_credentials_save(
    payload: LlmCredentialsUpdate, container: ContainerDep
) -> LlmCredentialsStatus:
    """Anahtarı kaydeder veya boşsa siler; istemciyi restart'sız yeniler."""
    body = await LlmCredentialsService(container).save(payload.api_key, payload.model)
    return LlmCredentialsStatus.model_validate(body)

@router.get(
    "/llm-credentials/reveal",
    response_model=LlmCredentialsReveal,
    summary="Bulut LLM anahtarını bir kez göster",
)
async def llm_credentials_reveal(container: ContainerDep) -> LlmCredentialsReveal:
    """Tam anahtar — router zaten token ister."""
    return LlmCredentialsReveal.model_validate(await LlmCredentialsService(container).reveal())

@router.delete(
    "/llm-credentials",
    response_model=LlmCredentialsStatus,
    summary="Kayıtlı bulut LLM anahtarını sil",
)
async def llm_credentials_delete(container: ContainerDep) -> LlmCredentialsStatus:
    """UI anahtarını siler ve ``.env`` yedeğine döner."""
    body = await LlmCredentialsService(container).save("", None)
    return LlmCredentialsStatus.model_validate(body)

@router.post("/error", response_model=OkResponse, summary="Son hatayı bildir")
async def report_error(payload: dict[str, str], system: SystemDep) -> OkResponse:
    """Masaüstü uygulamasının son hatasını sistem durumuna yazar."""
    system.set_last_error(payload.get("message"))
    return OkResponse(message="Hata kaydedildi.")
