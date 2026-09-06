"""Belge / RAG endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.api.deps import DatabaseDep, RAGDep
from app.core.errors import NotFoundError, ValidationError
from app.core.security import require_token
from app.db.repositories.document import DocumentRepository
from app.schemas.common import OkResponse
from app.schemas.document import (
    DocumentOut,
    DocumentSearchHit,
    DocumentSearchRequest,
    IngestPathRequest,
)

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_token)])

@router.get("", response_model=list[DocumentOut], summary="Belgeleri listele")
async def list_documents(
    database: DatabaseDep,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentOut]:
    """İndekslenmiş ve bekleyen belgeleri döndürür."""
    async with database.session() as session:
        records = await DocumentRepository(session).list_all(limit=limit, offset=offset)
        return [DocumentOut.model_validate(r) for r in records]

@router.get("/supported", summary="Desteklenen dosya türleri")
async def supported_types(rag: RAGDep) -> dict[str, list[str]]:
    """RAG'in kabul ettiği uzantılar."""
    return {"extensions": rag.supported_extensions()}

@router.get("/stats", summary="Belge ve vektör istatistikleri")
async def document_stats(rag: RAGDep) -> dict[str, object]:
    """Belge sayıları, chunk sayısı ve Qdrant collection boyutları."""
    return await rag.stats()

@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dosya yükle ve indeksle",
)
async def upload_documents(
    background: BackgroundTasks,
    rag: RAGDep,
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    """Bir veya daha fazla dosyayı yükler ve arka planda indeksler."""
    if not files:
        raise ValidationError("En az bir dosya gönderilmeli.")

    accepted: list[dict[str, object]] = []
    duplicates: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []

    for upload in files[:50]:
        try:
            content = await upload.read()
            result = await rag.ingest_upload(upload.filename or "dosya", content)
            if result["duplicate"]:
                duplicates.append(result)
            else:
                accepted.append(result)
                background.add_task(rag.process_document, str(result["document_id"]))
        except ValidationError as exc:
            failed.append({"filename": upload.filename, "reason": exc.user_message})
        finally:
            await upload.close()

    return {"accepted": accepted, "duplicates": duplicates, "failed": failed}

@router.post("/ingest-path", status_code=status.HTTP_202_ACCEPTED, summary="Yerel yolu indeksle")
async def ingest_path(
    payload: IngestPathRequest, background: BackgroundTasks, rag: RAGDep
) -> dict[str, object]:
    """İzin verilen bir klasör/dosya yolunu indeksler.

    Yol ``URYX_ALLOWED_PATHS`` altında olmalıdır; aksi hâlde 403 döner.
    """
    result = await rag.ingest_path(
        payload.path, recursive=payload.recursive, collection=payload.collection
    )
    for document_id in result["accepted"]:
        background.add_task(rag.process_document, document_id)
    return {
        "accepted_count": len(result["accepted"]),
        "accepted": result["accepted"],
        "skipped": result["skipped"],
    }

@router.post("/search", response_model=list[DocumentSearchHit], summary="Belgelerde ara")
async def search_documents(payload: DocumentSearchRequest, rag: RAGDep) -> list[DocumentSearchHit]:
    """Hybrid arama + rerank ile belge parçalarını döndürür."""
    return await rag.search(payload.query, top_k=payload.top_k, collection=payload.collection)

@router.post(
    "/{document_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OkResponse,
    summary="Belgeyi yeniden indeksle",
)
async def reindex_document(
    document_id: str, background: BackgroundTasks, rag: RAGDep, database: DatabaseDep
) -> OkResponse:
    """Belgeyi yeniden ayrıştırıp indeksler."""
    async with database.session() as session:
        if await DocumentRepository(session).get(document_id) is None:
            raise NotFoundError("Belge bulunamadı.")
    background.add_task(rag.reindex, document_id)
    return OkResponse(message="Yeniden indeksleme başlatıldı.")

@router.delete("/{document_id}", response_model=OkResponse, summary="Belgeyi sil")
async def delete_document(document_id: str, rag: RAGDep) -> OkResponse:
    """Belgeyi, parçalarını ve vektörlerini siler."""
    if not await rag.delete_document(document_id):
        raise NotFoundError("Belge bulunamadı.")
    return OkResponse(message="Belge silindi.")
