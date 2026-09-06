"""Ortak Pydantic şemaları."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

class ORMModel(BaseModel):
    """ORM nesnelerinden doğrudan doldurulabilen taban şema."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

class Page(BaseModel, Generic[T]):
    """Sayfalanmış liste cevabı."""

    items: list[T]
    total: int
    limit: int
    offset: int

class OkResponse(BaseModel):
    """Basit başarı cevabı."""

    ok: bool = True
    message: str | None = None

class ErrorBody(BaseModel):
    """Hata gövdesi."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

class ErrorResponse(BaseModel):
    """Standart hata cevabı."""

    error: ErrorBody
