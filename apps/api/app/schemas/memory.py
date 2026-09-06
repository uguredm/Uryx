"""Hafıza şemaları."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import MemoryCategory
from app.schemas.common import ORMModel

class MemoryOut(ORMModel):
    """Hafıza kaydı çıktısı."""

    id: str
    content: str
    category: str
    importance: float
    pinned: bool
    active: bool
    source: str
    source_conversation_id: str | None = None
    use_count: int
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)

class MemoryCreateRequest(BaseModel):
    """Manuel hafıza ekleme."""

    content: str = Field(min_length=3, max_length=4000)
    category: MemoryCategory = MemoryCategory.OTHER
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    pinned: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)

class MemoryUpdateRequest(BaseModel):
    """Hafıza güncelleme."""

    content: str | None = Field(default=None, min_length=3, max_length=4000)
    category: MemoryCategory | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    pinned: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

class MemorySearchRequest(BaseModel):
    """Semantik hafıza araması."""

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)

class MemoryStats(BaseModel):
    """Hafıza istatistikleri."""

    total: int
    pinned: int
    by_category: dict[str, int] = Field(default_factory=dict)

class MemoryEvaluationResult(BaseModel):
    """Memory evaluator çıktısı."""

    should_save: bool
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""
