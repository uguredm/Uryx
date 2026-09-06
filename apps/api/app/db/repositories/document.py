"""Belge ve chunk repository'leri.

``DocumentChunkRepository.sparse_search`` hybrid retrieval'in sparse ayağıdır:
PostgreSQL'de ``websearch_to_tsquery`` + ``ts_rank``, diğer sürücülerde
(SQLite testleri) ``LIKE`` tabanlı basit eşleşme kullanılır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, or_, select, text, update

from app.db.models import Document, DocumentChunk, DocumentStatus, utcnow
from app.db.repositories.base import BaseRepository

class DocumentRepository(BaseRepository[Document]):
    """Belge metadata'sı."""

    model = Document

    async def create(
        self,
        *,
        filename: str,
        extension: str,
        mime_type: str,
        size_bytes: int,
        content_hash: str,
        collection: str = "documents",
        source_path: str | None = None,
        stored_path: str | None = None,
    ) -> Document:
        """Yeni belge kaydı açar."""
        return await self.add(
            Document(
                filename=filename,
                extension=extension,
                mime_type=mime_type,
                size_bytes=size_bytes,
                content_hash=content_hash,
                collection=collection,
                source_path=source_path,
                stored_path=stored_path,
                status=DocumentStatus.PENDING,
            )
        )

    async def find_by_hash(self, content_hash: str) -> Document | None:
        """Aynı içerik hash'ine sahip belgeyi bulur (yinelenen yükleme kontrolü)."""
        stmt = select(Document).where(Document.content_hash == content_hash)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(
        self, *, limit: int = 200, offset: int = 0, status: DocumentStatus | None = None
    ) -> list[Document]:
        """Belgeleri en yeniden eskiye döndürür."""
        stmt = select(Document)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        stmt = stmt.order_by(desc(Document.created_at)).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        error: str | None = None,
        chunk_count: int | None = None,
    ) -> None:
        """Belgenin indeksleme durumunu günceller."""
        values: dict[str, Any] = {"status": status, "error": error}
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if status is DocumentStatus.INDEXED:
            values["indexed_at"] = utcnow()
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )

    async def stats(self) -> dict[str, Any]:
        """Belge sayıları ve toplam boyut."""
        rows = (
            await self.session.execute(
                select(Document.status, func.count()).group_by(Document.status)
            )
        ).all()
        by_status = {str(r[0].value if hasattr(r[0], "value") else r[0]): int(r[1]) for r in rows}
        total_size = int(
            (
                await self.session.execute(select(func.coalesce(func.sum(Document.size_bytes), 0)))
            ).scalar_one()
        )
        total_chunks = int(
            (
                await self.session.execute(select(func.coalesce(func.sum(Document.chunk_count), 0)))
            ).scalar_one()
        )
        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "total_size_bytes": total_size,
            "total_chunks": total_chunks,
        }

class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """Belge parçaları."""

    model = DocumentChunk

    async def bulk_create(
        self, document_id: str, chunks: list[dict[str, Any]]
    ) -> list[DocumentChunk]:
        """Parçaları toplu ekler."""
        entities = [
            DocumentChunk(
                id=chunk["id"],
                document_id=document_id,
                chunk_index=chunk["index"],
                content=chunk["content"],
                char_count=len(chunk["content"]),
                page=chunk.get("page"),
            )
            for chunk in chunks
        ]
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def delete_for_document(self, document_id: str) -> int:
        """Belgeye ait tüm parçaları siler."""
        result = await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        return int(result.rowcount or 0)

    async def get_many(self, ids: list[str]) -> list[DocumentChunk]:
        """Kimliklere göre parçaları döndürür."""
        if not ids:
            return []
        stmt = select(DocumentChunk).where(DocumentChunk.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def neighbors(
        self, document_id: str, chunk_index: int, window: int = 1
    ) -> dict[int, DocumentChunk]:
        """Aynı belgedeki komşu parçalar (sentence-window)."""
        if window <= 0:
            return {}
        rows = await self.range_for_document(
            document_id, max(0, chunk_index - window), chunk_index + window
        )
        return {row.chunk_index: row for row in rows if row.chunk_index != chunk_index}

    async def range_for_document(
        self, document_id: str, lo: int, hi: int
    ) -> list[DocumentChunk]:
        """Belgedeki ``lo..hi`` indeks aralığını sırayla döndürür."""
        if hi < lo:
            return []
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index >= lo,
                DocumentChunk.chunk_index <= hi,
            )
            .order_by(DocumentChunk.chunk_index)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def sparse_search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        """Full-text arama; ``(chunk_id, skor)`` çiftleri döndürür.

        PostgreSQL'de ``websearch_to_tsquery`` + ``ts_rank`` kullanılır. Diğer
        sürücülerde (test ortamı) kelime bazlı ``LIKE`` sayımına düşülür.
        """
        query = query.strip()
        if not query:
            return []

        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""

        if dialect == "postgresql":
            sql = text(
                """
                SELECT id,
                       ts_rank(
                           to_tsvector('simple', unaccent(content)),
                           websearch_to_tsquery('simple', unaccent(:q))
                       ) AS rank
                FROM document_chunks
                WHERE to_tsvector('simple', unaccent(content))
                      @@ websearch_to_tsquery('simple', unaccent(:q))
                ORDER BY rank DESC
                LIMIT :lim
                """
            )
            try:
                rows = (await self.session.execute(sql, {"q": query, "lim": limit})).all()
                return [(str(r[0]), float(r[1])) for r in rows]
            except Exception:
                await self.session.rollback()

        terms = [t for t in query.lower().split() if len(t) > 2][:8]
        if not terms:
            return []
        stmt = select(DocumentChunk.id, DocumentChunk.content)
        clauses = [func.lower(DocumentChunk.content).like(f"%{term}%") for term in terms]
        stmt = stmt.where(or_(*clauses)).limit(limit * 3)
        rows = (await self.session.execute(stmt)).all()

        scored: list[tuple[str, float]] = []
        for chunk_id, content in rows:
            lowered = content.lower()
            hits = sum(lowered.count(term) for term in terms)
            matched = sum(1 for term in terms if term in lowered)
            score = (matched / len(terms)) * 0.7 + min(hits / 10.0, 1.0) * 0.3
            scored.append((str(chunk_id), score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def count_since(self, since: datetime) -> int:
        """Belirli tarihten sonra eklenen parça sayısı."""
        stmt = (
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.created_at >= since)
        )
        return int((await self.session.execute(stmt)).scalar_one())
