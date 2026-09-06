"""RAG servisi — indeksleme ve sorgulama.

Akış:
``Document → Parse → Chunk → Embedding → Qdrant → Hybrid retrieval → Reranking → LLM``
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationError, VectorStoreUnavailableError
from app.core.logging import get_logger
from app.core.security import ensure_path_allowed
from app.db.models import DocumentStatus
from app.db.repositories.document import DocumentChunkRepository, DocumentRepository
from app.db.session import Database
from app.schemas.chat import SourceRef
from app.schemas.document import DocumentSearchHit
from app.services.rag.chunker import chunk_document
from app.services.rag.embeddings import SentenceTransformerProvider
from app.services.rag.parsers import (
    SUPPORTED_EXTENSIONS,
    classify,
    is_supported,
    iter_supported_files,
    parse_file,
)
from app.services.rag.retriever import (
    RetrievalCandidate,
    Reranker,
    autocut,
    cap_per_document,
    cluster_adjacent,
    create_reranker,
    distribution_based_fusion,
    expand_retrieval_query,
    filename_search_text,
    hybrid_vector_keyword,
    hypothetical_passage,
    keyword_overlap_score,
    lexical_with_title,
    lost_in_the_middle,
    mmr_select,
    reciprocal_rank_fusion,
    stitch_neighbor_text,
)
from app.services.rag.vector_store import QdrantVectorStore

logger = get_logger(__name__)

class RAGService:
    """Belge indeksleme ve geri getirme iş mantığı."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        vector_store: QdrantVectorStore,
        embeddings: SentenceTransformerProvider,
        reranker: Reranker | None = None,
    ) -> None:
        self._settings = settings
        self._db = database
        self._vectors = vector_store
        self._embeddings = embeddings
        self._reranker = reranker if reranker is not None else create_reranker(settings)
        self._indexing: set[str] = set()

    async def load_reranker(self) -> None:
        """Cross-encoder varsa önceden yükler; hata uygulamayı düşürmez."""
        load = getattr(self._reranker, "load", None)
        if callable(load):
            await load()

    async def ingest_upload(
        self, filename: str, content: bytes, *, collection: str | None = None
    ) -> dict[str, Any]:
        """Yüklenen dosyayı diske yazar ve indekslemeyi kuyruklar."""
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValidationError(
                f"'{extension or filename}' desteklenmeyen bir dosya türü.",
                details={"supported": sorted(SUPPORTED_EXTENSIONS)},
            )

        max_bytes = self._settings.rag_max_file_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValidationError(
                f"Dosya çok büyük ({len(content) / 1e6:.1f} MB). "
                f"Sınır: {self._settings.rag_max_file_mb} MB."
            )

        content_hash = hashlib.sha256(content).hexdigest()
        auto_collection, mime = classify(filename)
        target_collection = collection or auto_collection

        upload_root = Path(self._settings.upload_dir)
        upload_root.mkdir(parents=True, exist_ok=True)
        stored_path = upload_root / f"{content_hash[:16]}{extension}"

        async with self._db.session() as session:
            documents = DocumentRepository(session)
            existing = await documents.find_by_hash(content_hash)
            if existing is not None:
                return {
                    "duplicate": True,
                    "document_id": existing.id,
                    "filename": existing.filename,
                }
            await asyncio.to_thread(stored_path.write_bytes, content)
            document = await documents.create(
                filename=Path(filename).name,
                extension=extension,
                mime_type=mime,
                size_bytes=len(content),
                content_hash=content_hash,
                collection=target_collection,
                stored_path=str(stored_path),
            )
            document_id = document.id

        return {"duplicate": False, "document_id": document_id, "filename": Path(filename).name}

    async def ingest_path(
        self, raw_path: str, *, recursive: bool = True, collection: str | None = None
    ) -> dict[str, Any]:
        """İzin verilen bir yerel yoldan dosya/klasör indeksler."""
        path = ensure_path_allowed(raw_path, self._settings)
        if not path.exists():
            raise NotFoundError(f"Yol bulunamadı: {raw_path}")

        files = iter_supported_files(path, recursive=recursive)
        if not files:
            raise ValidationError(
                "Belirtilen yolda desteklenen dosya bulunamadı.",
                details={"supported": sorted(SUPPORTED_EXTENSIONS)},
            )

        accepted: list[str] = []
        skipped: list[dict[str, Any]] = []
        max_bytes = self._settings.rag_max_file_mb * 1024 * 1024

        async with self._db.session() as session:
            documents = DocumentRepository(session)
            for file_path in files[:500]:
                try:
                    size = file_path.stat().st_size
                    if size > max_bytes or size == 0:
                        skipped.append({"path": str(file_path), "reason": "boyut sınırı"})
                        continue
                    content_hash = await asyncio.to_thread(_hash_file, file_path)
                    if await documents.find_by_hash(content_hash) is not None:
                        skipped.append({"path": str(file_path), "reason": "zaten indeksli"})
                        continue
                    auto_collection, mime = classify(file_path)
                    document = await documents.create(
                        filename=file_path.name,
                        extension=file_path.suffix.lower(),
                        mime_type=mime,
                        size_bytes=size,
                        content_hash=content_hash,
                        collection=collection or auto_collection,
                        source_path=str(file_path),
                        stored_path=str(file_path),
                    )
                    accepted.append(document.id)
                except OSError as exc:
                    skipped.append({"path": str(file_path), "reason": str(exc)})

        return {"accepted": accepted, "skipped": skipped}

    async def process_document(self, document_id: str) -> None:
        """Belgeyi ayrıştırır, parçalar, gömer ve Qdrant'a yazar."""
        if document_id in self._indexing:
            return
        self._indexing.add(document_id)
        try:
            await self._process_document_inner(document_id)
        except Exception as exc:
            logger.error("index_failed", document_id=document_id, error=str(exc))
            async with self._db.session() as session:
                await DocumentRepository(session).set_status(
                    document_id, DocumentStatus.FAILED, error=str(exc)[:1000]
                )
        finally:
            self._indexing.discard(document_id)

    async def _process_document_inner(self, document_id: str) -> None:
        """``process_document`` gövdesi."""
        async with self._db.session() as session:
            document = await DocumentRepository(session).get(document_id)
            if document is None:
                raise NotFoundError("Belge bulunamadı.")
            source = document.stored_path or document.source_path
            filename = document.filename
            collection = document.collection
            await DocumentRepository(session).set_status(document_id, DocumentStatus.PARSING)

        if not source or not Path(source).exists():
            raise NotFoundError(f"Belge dosyası diskte yok: {source}")

        parsed = await parse_file(Path(source))
        if parsed.error and parsed.is_empty:
            raise ValidationError(parsed.error)
        if parsed.is_empty:
            raise ValidationError("Belgeden okunabilir metin çıkarılamadı.")

        chunks = chunk_document(
            parsed,
            chunk_size=self._settings.rag_chunk_size,
            overlap=self._settings.rag_chunk_overlap,
            min_chars=self._settings.rag_min_chunk_chars,
        )
        if not chunks:
            raise ValidationError("Belge parçalanamadı (içerik çok kısa).")

        async with self._db.session() as session:
            await DocumentRepository(session).set_status(document_id, DocumentStatus.EMBEDDING)
            chunk_repo = DocumentChunkRepository(session)
            await chunk_repo.delete_for_document(document_id)
            await chunk_repo.bulk_create(document_id, [c.to_dict() for c in chunks])

        vectors = await self._embeddings.embed(
            [_embed_passage(filename, c.content) for c in chunks]
        )

        if not self._vectors.available:
            await self._vectors.ping()
        written = 0
        if self._vectors.available:
            written = await self._vectors.upsert(
                collection,
                ids=[c.id for c in chunks],
                vectors=vectors,
                payloads=[
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "chunk_index": c.index,
                        "page": c.page,
                        "content": c.content[:2000],
                    }
                    for c in chunks
                ],
            )

        async with self._db.session() as session:
            await DocumentRepository(session).set_status(
                document_id,
                DocumentStatus.INDEXED,
                chunk_count=len(chunks),
                error=None if written else "Qdrant'a yazılamadı; yalnızca metin araması aktif.",
            )
        logger.info(
            "document_indexed", document_id=document_id, chunks=len(chunks), vectors=written
        )

    async def reindex(self, document_id: str) -> None:
        """Belgeyi yeniden indeksler."""
        async with self._db.session() as session:
            document = await DocumentRepository(session).get(document_id)
            if document is None:
                raise NotFoundError("Belge bulunamadı.")
            collection = document.collection
        await self._vectors.delete_by_filter(collection, {"document_id": document_id})
        await self.process_document(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """Belgeyi, parçalarını ve vektörlerini siler."""
        async with self._db.session() as session:
            repo = DocumentRepository(session)
            document = await repo.get(document_id)
            if document is None:
                return False
            collection = document.collection
            stored = document.stored_path
            source = document.source_path
            await DocumentChunkRepository(session).delete_for_document(document_id)
            await repo.delete(document_id)

        await self._vectors.delete_by_filter(collection, {"document_id": document_id})

        if stored and stored != source and stored.startswith(self._settings.upload_dir):
            with suppress(OSError):
                await asyncio.to_thread(Path(stored).unlink, True)
        return True

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        collection: str = "documents",
    ) -> list[RetrievalCandidate]:
        """Hybrid arama + rerank ile en iyi parçaları döndürür."""
        query = query.strip()
        if not query:
            return []

        search_query = expand_retrieval_query(query)
        hyde_query = hypothetical_passage(query)
        top_k = top_k or self._settings.rag_top_k
        candidate_k = max(self._settings.rag_candidate_k, top_k * 3)

        dense: list[tuple[str, float]] = []
        if self._vectors.available:
            try:
                vector = await self._embeddings.embed_query(hyde_query)
                hits = await self._vectors.search(
                    collection, vector=vector, limit=candidate_k, score_threshold=None
                )
                dense = [(h.id, h.score) for h in hits]
            except Exception as exc:
                logger.warning("dense_search_failed", error=str(exc))

        sparse: list[tuple[str, float]] = []
        if self._db.available:
            try:
                async with self._db.session() as session:
                    sparse = await DocumentChunkRepository(session).sparse_search(
                        search_query, limit=candidate_k
                    )
            except Exception as exc:
                logger.warning("sparse_search_failed", error=str(exc))

        if not dense and not sparse:
            return []

        fused = reciprocal_rank_fusion(dense, sparse)
        dbsf = distribution_based_fusion(dense, sparse)
        dense_scores = dict(dense)
        sparse_scores = dict(sparse)

        candidates = await self._hydrate(list(fused), fused, dense_scores, sparse_scores)
        for item in candidates:
            vector_sim = dbsf.get(item.chunk_id, 0.0)
            item.fused_score = hybrid_vector_keyword(
                vector_sim, search_query, item.content, item.filename
            )
            item.signals = {
                **item.signals,
                "keyword": lexical_with_title(
                    search_query, item.content, item.filename
                ),
                "title": keyword_overlap_score(
                    search_query, filename_search_text(item.filename)
                ),
                "dbsf": round(vector_sim, 4),
            }
        pool_k = max(top_k * 3, min(len(candidates), candidate_k))
        ranked = await self._reranker.rerank(search_query, candidates, pool_k)
        ranked = autocut(ranked, jumps=1)
        selected = mmr_select(
            ranked, top_k, lambda_mult=self._settings.rag_mmr_lambda
        )
        selected = cap_per_document(selected)
        expanded = await self._expand_windows(selected)
        expanded = await self._promote_small_docs(expanded)
        kept = [c for c in expanded if c.final_score >= self._settings.rag_min_score]
        return lost_in_the_middle(kept)

    async def _hydrate(
        self,
        chunk_ids: list[str],
        fused: dict[str, float],
        dense_scores: dict[str, float],
        sparse_scores: dict[str, float],
    ) -> list[RetrievalCandidate]:
        """Chunk kimliklerini veritabanı içerikleriyle doldurur."""
        if not self._db.available:
            return []
        async with self._db.session() as session:
            chunks = await DocumentChunkRepository(session).get_many(chunk_ids)
            documents = DocumentRepository(session)
            filenames: dict[str, str] = {}
            for chunk in chunks:
                if chunk.document_id not in filenames:
                    document = await documents.get(chunk.document_id)
                    filenames[chunk.document_id] = document.filename if document else "belge"

            return [
                RetrievalCandidate(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filenames.get(chunk.document_id, "belge"),
                    content=chunk.content,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    dense_score=dense_scores.get(chunk.id, 0.0),
                    sparse_score=sparse_scores.get(chunk.id, 0.0),
                    fused_score=fused.get(chunk.id, 0.0),
                )
                for chunk in chunks
            ]

    async def _expand_windows(
        self, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        """PrivateGPT/LlamaIndex small-to-big: komşuları birleştir, bitişikleri tek pasaj yap."""
        window = self._settings.rag_neighbor_window
        if not candidates or not self._db.available:
            return candidates

        clusters = cluster_adjacent(candidates, gap=max(1, window))
        expanded: list[RetrievalCandidate] = []
        async with self._db.session() as session:
            repo = DocumentChunkRepository(session)
            for cluster in clusters:
                leader = max(cluster, key=lambda item: item.final_score)
                if window <= 0 and len(cluster) == 1:
                    expanded.append(leader)
                    continue
                if len(cluster) == 1:
                    extra = await repo.neighbors(
                        leader.document_id, leader.chunk_index, window
                    )
                    prev_hit = extra.get(leader.chunk_index - 1)
                    next_hit = extra.get(leader.chunk_index + 1)
                    leader.content = stitch_neighbor_text(
                        leader.content,
                        prev_hit.content if prev_hit else None,
                        next_hit.content if next_hit else None,
                        max_chars=2400,
                    )
                    leader.signals = {**leader.signals, "window": float(len(extra) + 1)}
                    expanded.append(leader)
                    continue
                cluster_lo = min(item.chunk_index for item in cluster)
                cluster_hi = max(item.chunk_index for item in cluster)
                lo = max(0, cluster_lo - window)
                hi = cluster_hi + window
                rows = await repo.range_for_document(leader.document_id, lo, hi)
                by_index = {row.chunk_index: row for row in rows}
                center_rows = [
                    row for row in rows if cluster_lo <= row.chunk_index <= cluster_hi
                ]
                center_text = (
                    "\n".join(row.content for row in center_rows).strip()
                    if center_rows
                    else leader.content
                )
                prev_row = by_index.get(cluster_lo - 1)
                next_row = by_index.get(cluster_hi + 1)
                leader.content = stitch_neighbor_text(
                    center_text,
                    prev_row.content if prev_row else None,
                    next_row.content if next_row else None,
                    max_chars=2400,
                )
                leader.signals = {**leader.signals, "window": float(len(rows))}
                expanded.append(leader)
        return expanded

    async def _promote_small_docs(
        self, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        """Open WebUI full-context: 1–3 parçalık belgede tüm metni ver."""
        if not candidates or not self._db.available:
            return candidates
        async with self._db.session() as session:
            documents = DocumentRepository(session)
            chunks = DocumentChunkRepository(session)
            for candidate in candidates:
                document = await documents.get(candidate.document_id)
                count = int(getattr(document, "chunk_count", 0) or 0) if document else 0
                if count < 2 or count > 3:
                    continue
                rows = await chunks.range_for_document(candidate.document_id, 0, count)
                joined = "\n".join(row.content for row in rows).strip()
                if 0 < len(joined) <= 3200:
                    candidate.content = joined
                    candidate.signals = {**candidate.signals, "full_context": 1.0}
        return candidates

    async def search(
        self, query: str, *, top_k: int = 5, collection: str = "documents"
    ) -> list[DocumentSearchHit]:
        """API için arama sonuçları."""
        candidates = await self.retrieve(query, top_k=top_k, collection=collection)
        return [
            DocumentSearchHit(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                content=c.content,
                score=c.final_score,
                page=c.page,
            )
            for c in candidates
        ]

    @staticmethod
    def to_source_refs(candidates: list[RetrievalCandidate]) -> list[SourceRef]:
        """Adayları API/WS kaynak referanslarına çevirir."""
        return [
            SourceRef(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                score=round(c.final_score, 4),
                snippet=c.content[:900].strip(),
                page=c.page,
            )
            for c in candidates
        ]

    async def stats(self) -> dict[str, Any]:
        """Belge ve vektör istatistikleri."""
        db_stats: dict[str, Any] = {}
        if self._db.available:
            async with self._db.session() as session:
                db_stats = await DocumentRepository(session).stats()
        return {
            **db_stats,
            "vectors": await self._vectors.stats(),
            "embedding_model": self._embeddings.model_name,
            "embedding_fallback": self._embeddings.using_fallback,
            "vector_store_available": self._vectors.available,
        }

    async def require_vector_store(self) -> None:
        """Qdrant kullanılabilir değilse hata fırlatır."""
        if not self._vectors.available and not await self._vectors.ping():
            raise VectorStoreUnavailableError()

    @staticmethod
    def supported_extensions() -> list[str]:
        """Desteklenen dosya uzantıları."""
        return sorted(SUPPORTED_EXTENSIONS)

    @staticmethod
    def is_supported_file(path: str) -> bool:
        """Yol desteklenen bir dosya mı?"""
        return is_supported(path)

def _embed_passage(filename: str, content: str) -> str:
    """AnythingLLM ``chunkHeaderMeta``: gömme metnine kaynak adı ekler, depo metni temiz kalır."""
    stem = Path(filename).stem.strip() if filename else ""
    if not stem:
        return content
    return f"Kaynak: {stem}\n{content}"

def _hash_file(path: Path) -> str:
    """Dosyanın SHA-256 özetini hesaplar."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
