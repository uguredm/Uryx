"""Merkezi uygulama ayarları.

Tüm yapılandırma ortam değişkenlerinden okunur; kod içinde hardcoded değer
bulunmaz. Ayarlar tek bir ``Settings`` nesnesinde toplanır ve
``get_settings()`` ile önbelleklenerek dağıtılır (Dependency Injection).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_repo_root(start: Path) -> Path:
    """Monorepo veya container kopyasındaki ayar dosyası kökünü bulur."""
    for candidate in (start, *start.parents):
        if (
            (candidate / ".env.example").exists()
            or (candidate / "docker-compose.yml").exists()
            or (candidate / "pyproject.toml").exists()
        ):
            return candidate
    return start.parents[2] if len(start.parents) > 2 else start

_REPO_ROOT = _find_repo_root(Path(__file__).resolve())

class Settings(BaseSettings):
    """Uygulamanın tüm ayarları."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Uryx API"
    app_version: str = "1.0.0"
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    uryx_local_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "uryx_local_token", "URYX_LOCAL_TOKEN", "JARVIS_LOCAL_TOKEN"
        ),
    )
    uryx_bind_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("uryx_bind_host", "URYX_BIND_HOST", "JARVIS_BIND_HOST"),
    )
    uryx_cors_origins: str = Field(
        default="http://localhost:5173,app://.",
        validation_alias=AliasChoices(
            "uryx_cors_origins", "URYX_CORS_ORIGINS", "JARVIS_CORS_ORIGINS"
        ),
    )
    uryx_allowed_paths: str = Field(
        default="",
        validation_alias=AliasChoices(
            "uryx_allowed_paths", "URYX_ALLOWED_PATHS", "JARVIS_ALLOWED_PATHS"
        ),
    )
    require_tool_confirmation: bool = True

    database_url: str = "postgresql+asyncpg://jarvis:jarvis_local_dev_password@postgres:5432/jarvis"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    qdrant_url: str = "http://qdrant:6333"
    qdrant_timeout: int = 20
    qdrant_collection_memory: str = "uryx_memory"
    qdrant_collection_documents: str = "uryx_documents"
    qdrant_collection_conversations: str = "uryx_conversations"
    qdrant_collection_code: str = "uryx_code"

    vllm_url: str = "http://llm:8000/v1"
    vllm_api_key: str = "EMPTY"
    llm_model: str = "qwen3-8b"
    llm_gguf_file: str = "Qwen3-8B-Q4_K_M.gguf"
    llm_max_model_len: int = 8192
    llm_n_gpu_layers: int = Field(default=99, ge=0, le=999)

    llm_gpu_memory_utilization: float = Field(default=0.70, ge=0.1, le=0.98)
    llm_max_num_seqs: int = 4
    llm_temperature: float = 0.7
    llm_top_p: float = 0.8
    llm_max_tokens: int = 1024
    llm_request_timeout: int = 180
    llm_enable_thinking: bool = False
    llm_concise_mode: bool = False

    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    gemini_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_request_timeout: int = 180
    gemini_allow_private_context: bool = False
    cloud_provider: str = "gemini"
    llm_routing_mode: Literal["local", "hybrid", "gemini"] = "hybrid"

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16

    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 5
    rag_candidate_k: int = 20
    rag_min_score: float = 0.25
    rag_max_file_mb: int = 50
    rag_neighbor_window: int = Field(default=1, ge=0, le=3)
    rag_min_chunk_chars: int = Field(default=180, ge=0, le=800)
    rag_mmr_lambda: float = Field(default=0.72, ge=0.0, le=1.0)
    rag_rerank_enabled: bool = True
    rag_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rag_rerank_device: str = "cpu"
    upload_dir: str = "/data/uploads"

    memory_auto_enabled: bool = True
    memory_top_k: int = 5
    memory_min_score: float = 0.20
    memory_evaluator_max_tokens: int = 512
    memory_recency_half_life_days: float = Field(default=14.0, ge=1.0, le=365.0)
    memory_semantic_dedup_score: float = Field(default=0.93, ge=0.8, le=0.99)
    memory_episode_enabled: bool = True
    memory_core_min_importance: float = Field(default=0.8, ge=0.5, le=1.0)
    memory_core_slots: int = Field(default=2, ge=0, le=5)

    whisper_url: str = "http://whisper:8090"
    whisper_model: str = "medium"
    whisper_language: str = "tr"
    whisper_timeout: int = 120

    tts_url: str = "http://tts:8091"
    tts_voice: str = "tr_TR-dfki-medium"
    tts_speed: float = 1.0
    tts_volume: float = 1.0
    tts_enabled: bool = True
    tts_sentence_streaming: bool = True
    tts_timeout: int = 60

    wake_word_enabled: bool = False
    wake_word: str = "uryx"
    wake_word_sensitivity: float = 0.6

    system_metrics_interval: float = Field(default=3.0, ge=0.5, le=60.0)
    docker_health_interval: float = Field(default=10.0, ge=1.0, le=300.0)
    host_tool_timeout: float = 60.0

    host_tool_retries: int = Field(default=2, ge=0, le=5)
    host_tool_retry_delay: float = Field(default=0.35, ge=0.0, le=5.0)

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return "INFO"
        return level

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origin listesini döndürür."""
        return [o.strip() for o in self.uryx_cors_origins.split(",") if o.strip()]

    @property
    def allowed_path_list(self) -> list[str]:
        """Dosya erişimine izin verilen kök dizinler."""
        raw = self.uryx_allowed_paths.strip()
        if not raw:
            return []
        separator = ";" if ";" in raw else ","
        return [p.strip() for p in raw.split(separator) if p.strip()]

    @property
    def auth_enabled(self) -> bool:
        """Local token doğrulaması etkin mi?"""
        return bool(self.uryx_local_token.strip())

    @property
    def sync_database_url(self) -> str:
        """Alembic için senkron sürücülü DSN."""
        return self.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql://")

    def qdrant_collections(self) -> dict[str, str]:
        """Mantıksal ad → Qdrant collection adı eşlemesi."""
        return {
            "memory": self.qdrant_collection_memory,
            "documents": self.qdrant_collection_documents,
            "conversations": self.qdrant_collection_conversations,
            "code": self.qdrant_collection_code,
        }

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Önbelleklenmiş ayar nesnesini döndürür."""
    return Settings()

def reset_settings_cache() -> None:
    """Test amaçlı: ayar önbelleğini temizler."""
    get_settings.cache_clear()
    os.environ.pop("_URYX_SETTINGS_CACHED", None)
    os.environ.pop("_JARVIS_SETTINGS_CACHED", None)
