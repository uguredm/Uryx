"""Hafıza yönetimi endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import MemoryDep
from app.core.errors import NotFoundError
from app.core.security import require_token
from app.db.models import MemoryCategory
from app.schemas.chat import MemoryRef
from app.schemas.common import OkResponse
from app.schemas.memory import (
    MemoryCreateRequest,
    MemoryOut,
    MemorySearchRequest,
    MemoryStats,
    MemoryUpdateRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_token)])

@router.get("", response_model=list[MemoryOut], summary="Hafıza kayıtlarını listele")
async def list_memories(
    memory: MemoryDep,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    category: MemoryCategory | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
) -> list[MemoryOut]:
    """Aktif hafıza kayıtlarını döndürür (sabitlenmişler önce)."""
    records = await memory.list(limit=limit, offset=offset, category=category, query=q)
    return [MemoryOut.model_validate(r) for r in records]

@router.post(
    "", response_model=MemoryOut, status_code=status.HTTP_201_CREATED, summary="Manuel hafıza ekle"
)
async def create_memory(payload: MemoryCreateRequest, memory: MemoryDep) -> MemoryOut:
    """Kullanıcının elle girdiği bilgiyi kalıcı hafızaya ekler."""
    record = await memory.create(
        payload.content,
        category=payload.category,
        importance=payload.importance,
        pinned=payload.pinned,
        tags=payload.tags,
        source="manual",
    )
    return MemoryOut.model_validate(record)

@router.get("/stats", response_model=MemoryStats, summary="Hafıza istatistikleri")
async def memory_stats(memory: MemoryDep) -> MemoryStats:
    """Kategori bazlı hafıza sayıları."""
    return MemoryStats(**await memory.stats())

@router.post("/search", response_model=list[MemoryRef], summary="Hafızada semantik arama")
async def search_memory(payload: MemorySearchRequest, memory: MemoryDep) -> list[MemoryRef]:
    """Sorguya en yakın hafıza kayıtlarını döndürür."""
    return await memory.search(payload.query, top_k=payload.top_k)

@router.patch("/{memory_id}", response_model=MemoryOut, summary="Hafıza kaydını güncelle")
async def update_memory(
    memory_id: str, payload: MemoryUpdateRequest, memory: MemoryDep
) -> MemoryOut:
    """Hafıza kaydının içeriğini/kategorisini/önemini günceller."""
    record = await memory.update(memory_id, **payload.model_dump(exclude_unset=True))
    return MemoryOut.model_validate(record)

@router.post("/{memory_id}/pin", response_model=OkResponse, summary="Hafızayı sabitle")
async def pin_memory(
    memory_id: str, memory: MemoryDep, pinned: bool = Query(default=True)
) -> OkResponse:
    """Kaydı sabitler veya sabiti kaldırır."""
    await memory.set_pinned(memory_id, pinned)
    return OkResponse(message="Sabitlendi." if pinned else "Sabit kaldırıldı.")

@router.delete("/{memory_id}", response_model=OkResponse, summary="Hafıza kaydını sil")
async def delete_memory(memory_id: str, memory: MemoryDep) -> OkResponse:
    """Kaydı kalıcı olarak siler."""
    if not await memory.delete(memory_id):
        raise NotFoundError("Hafıza kaydı bulunamadı.")
    return OkResponse(message="Hafıza kaydı silindi.")

@router.post("/reindex", response_model=OkResponse, summary="Hafıza vektörlerini yenile")
async def reindex_memory(memory: MemoryDep) -> OkResponse:
    """Tüm hafıza kayıtlarının vektörlerini yeniden üretir."""
    count = await memory.reindex_all()
    return OkResponse(message=f"{count} hafıza kaydı yeniden indekslendi.")
