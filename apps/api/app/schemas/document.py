"""Belge / RAG şemaları."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

class DocumentOut(ORMModel):
    """Belge çıktısı."""

    id: str
    filename: str
    source_path: str | None = None
    mime_type: str
    extension: str
    size_bytes: int
    collection: str
    status: str
    chunk_count: int
    error: str | None = None
    created_at: datetime
    indexed_at: datetime | None = None

class IngestPathRequest(BaseModel):
    """Yerel dosya/klasör yolundan indeksleme isteği.

    Yol, ``URYX_ALLOWED_PATHS`` altında olmak zorundadır.
    """

    path: str = Field(min_length=1, max_length=4000)
    recursive: bool = True
    collection: str = Field(default="documents", pattern=r"^(documents|code)$")

class ReindexRequest(BaseModel):
    """Yeniden indeksleme."""

    document_id: str

class DocumentSearchRequest(BaseModel):
    """Belge araması."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    collection: str = Field(default="documents")

class DocumentSearchHit(BaseModel):
    """Arama sonucu."""

    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    page: int | None = None

class DocumentStats(BaseModel):
    """Belge istatistikleri."""

    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    total_size_bytes: int = 0
    total_chunks: int = 0

class IngestResult(BaseModel):
    """İndeksleme sonucu."""

    accepted: list[DocumentOut] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
