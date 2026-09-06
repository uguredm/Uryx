"""Qdrant vektör deposu sarmalayıcısı.

Dört mantıksal collection yönetilir: ``memory``, ``documents``,
``conversations``, ``code``. Belge RAG'i ile kişisel hafıza kasıtlı olarak
ayrı collection'larda tutulur.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.rag.qdrant_migrate import CopyReport, filter_copy_points, legacy_copy_specs

logger = get_logger(__name__)

@dataclass(slots=True)
class VectorHit:
    """Vektör arama sonucu."""

    id: str
    score: float
    payload: dict[str, Any]

class QdrantVectorStore:
    """Qdrant istemcisi üzerinde ince bir hizmet katmanı."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncQdrantClient | None = None
        self.available = False
        self.last_error: str | None = None
        self._dimension = settings.embedding_dim

    async def connect(self, dimension: int | None = None) -> None:
        """İstemciyi kurar ve collection'ları hazırlar."""
        if dimension:
            self._dimension = dimension
        try:
            self._client = AsyncQdrantClient(
                url=self._settings.qdrant_url,
                timeout=self._settings.qdrant_timeout,
                prefer_grpc=False,
            )
            await self._client.get_collections()
            self.available = True
            self.last_error = None
            await self.ensure_collections()
            try:
                await self.copy_legacy_collections()
            except Exception as exc:
                logger.warning("qdrant_legacy_copy_failed", error=str(exc))
            logger.info("qdrant_connected", url=self._settings.qdrant_url, dim=self._dimension)
        except Exception as exc:
            self.available = False
            self.last_error = str(exc)
            logger.warning("qdrant_unavailable", error=str(exc))

    async def disconnect(self) -> None:
        """İstemciyi kapatır."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self.available = False

    async def ping(self) -> bool:
        """Bağlantıyı doğrular."""
        if self._client is None:
            return False
        try:
            await self._client.get_collections()
            self.available = True
            self.last_error = None
        except Exception as exc:
            self.available = False
            self.last_error = str(exc)
        return self.available

    async def ensure_collections(self) -> None:
        """Eksik collection'ları oluşturur."""
        if self._client is None:
            return
        existing = {c.name for c in (await self._client.get_collections()).collections}
        for logical, name in self._settings.qdrant_collections().items():
            if name in existing:
                continue
            await self._client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self._dimension, distance=models.Distance.COSINE
                ),
                optimizers_config=models.OptimizersConfigDiff(default_segment_number=2),
            )
            logger.info("qdrant_collection_created", logical=logical, name=name)

    async def copy_legacy_collections(self) -> dict[str, CopyReport]:
        """``jarvis_*`` → ayarlardaki ``uryx_*``. Kaynak silinmez; recreate yok."""
        reports: dict[str, CopyReport] = {}
        if self._client is None:
            return reports
        existing = {c.name for c in (await self._client.get_collections()).collections}
        await self.ensure_collections()
        existing = {c.name for c in (await self._client.get_collections()).collections}
        for spec in legacy_copy_specs(existing, self._settings.qdrant_collections()):
            reports[spec.logical] = await self._copy_named_collection(spec.source, spec.target)
        return reports

    async def _copy_named_collection(self, source: str, target: str) -> CopyReport:
        assert self._client is not None
        offset: int | str | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=source,
                limit=64,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            rows: list[dict] = []
            for record in records:
                vector = record.vector
                if isinstance(vector, dict):
                    vector = next(iter(vector.values()), [])
                rows.append(
                    {
                        "id": str(record.id),
                        "vector": list(vector or []),
                        "payload": dict(record.payload or {}),
                    }
                )
            kept = filter_copy_points(rows, dimension=self._dimension)
            if kept:
                points = [
                    models.PointStruct(
                        id=self._point_id(row["id"]),
                        vector=row["vector"],
                        payload=row["payload"],
                    )
                    for row in kept
                ]
                await self._client.upsert(collection_name=target, points=points, wait=True)
            if not records or offset is None:
                break
        source_count = await self._count_named(source)
        target_count = await self._count_named(target)
        logger.info(
            "qdrant_legacy_copied",
            source=source,
            target=target,
            source_count=source_count,
            target_count=target_count,
        )
        return CopyReport(source_count=source_count, target_count=target_count)

    def _point_id(self, value: str) -> str:
        return self.to_point_id(value)

    async def _count_named(self, name: str) -> int:
        if self._client is None:
            return 0
        result = await self._client.count(collection_name=name, exact=False)
        return int(result.count)

    def _collection(self, logical: str) -> str:
        """Mantıksal adı gerçek collection adına çevirir."""
        mapping = self._settings.qdrant_collections()
        if logical not in mapping:
            raise ValueError(f"Bilinmeyen collection: {logical}")
        return mapping[logical]

    @staticmethod
    def to_point_id(value: str) -> str:
        """Herhangi bir string'i geçerli bir Qdrant UUID kimliğine çevirir."""
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError):
            return str(uuid.uuid5(uuid.NAMESPACE_URL, str(value)))

    async def upsert(
        self,
        logical: str,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        """Noktaları ekler/günceller; yazılan nokta sayısını döndürür."""
        if self._client is None or not ids:
            return 0
        points = [
            models.PointStruct(
                id=self.to_point_id(pid),
                vector=vector,
                payload={**payload, "_source_id": pid},
            )
            for pid, vector, payload in zip(ids, vectors, payloads, strict=True)
        ]
        try:
            await self._client.upsert(
                collection_name=self._collection(logical), points=points, wait=True
            )
            return len(points)
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("qdrant_upsert_failed", logical=logical, error=str(exc))
            return 0

    async def search(
        self,
        logical: str,
        *,
        vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Vektör araması yapar."""
        if self._client is None:
            return []
        query_filter = _build_filter(filters)
        try:
            response = await self._client.query_points(
                collection_name=self._collection(logical),
                query=vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
            )
            return [
                VectorHit(
                    id=str((p.payload or {}).get("_source_id", p.id)),
                    score=float(p.score),
                    payload=dict(p.payload or {}),
                )
                for p in response.points
            ]
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("qdrant_search_failed", logical=logical, error=str(exc))
            return []

    async def delete(self, logical: str, ids: list[str]) -> int:
        """Verilen kimliklere sahip noktaları siler."""
        if self._client is None or not ids:
            return 0
        try:
            await self._client.delete(
                collection_name=self._collection(logical),
                points_selector=models.PointIdsList(points=[self.to_point_id(i) for i in ids]),
                wait=True,
            )
            return len(ids)
        except Exception as exc:
            logger.error("qdrant_delete_failed", logical=logical, error=str(exc))
            return 0

    async def delete_by_filter(self, logical: str, filters: dict[str, Any]) -> bool:
        """Filtreye uyan tüm noktaları siler."""
        if self._client is None:
            return False
        query_filter = _build_filter(filters)
        if query_filter is None:
            return False
        try:
            await self._client.delete(
                collection_name=self._collection(logical),
                points_selector=models.FilterSelector(filter=query_filter),
                wait=True,
            )
            return True
        except Exception as exc:
            logger.error("qdrant_delete_filter_failed", logical=logical, error=str(exc))
            return False

    async def count(self, logical: str) -> int:
        """Collection'daki nokta sayısı."""
        if self._client is None:
            return 0
        try:
            result = await self._client.count(
                collection_name=self._collection(logical), exact=False
            )
            return int(result.count)
        except Exception:
            return 0

    async def stats(self) -> dict[str, int]:
        """Tüm collection'ların nokta sayıları."""
        if self._client is None:
            return {}
        logical_names = list(self._settings.qdrant_collections())
        counts = await asyncio.gather(*(self.count(name) for name in logical_names))
        return dict(zip(logical_names, counts, strict=True))

    async def recreate(self, logical: str) -> bool:
        """Collection'ı siler ve yeniden oluşturur."""
        if self._client is None:
            return False
        try:
            await self._client.delete_collection(self._collection(logical))
            await self.ensure_collections()
            return True
        except Exception as exc:
            logger.error("qdrant_recreate_failed", logical=logical, error=str(exc))
            return False

def _build_filter(filters: dict[str, Any] | None) -> models.Filter | None:
    """Basit eşitlik sözlüğünü Qdrant filtresine çevirir."""
    if not filters:
        return None
    conditions: list[models.FieldCondition] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set):
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchAny(any=list(value)))
            )
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=conditions) if conditions else None
