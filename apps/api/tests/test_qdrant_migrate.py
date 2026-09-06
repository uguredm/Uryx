"""Qdrant jarvis_* → uryx_* kopya (wipe yok, dim 384)."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.config import Settings
from app.services.rag.qdrant_migrate import (
    LEGACY_COLLECTIONS,
    filter_copy_points,
    legacy_copy_specs,
)

class TestCollectionDefaults:
    def test_varsayilan_adlar_uryx_dim_384(self) -> None:
        fields = Settings.model_fields
        assert fields["embedding_dim"].default == 384
        assert fields["qdrant_collection_memory"].default == "uryx_memory"
        assert fields["qdrant_collection_documents"].default == "uryx_documents"
        assert fields["qdrant_collection_conversations"].default == "uryx_conversations"
        assert fields["qdrant_collection_code"].default == "uryx_code"

    def test_eski_jarvis_adlari_kaynak_olarak_durur(self) -> None:
        assert LEGACY_COLLECTIONS["memory"] == "jarvis_memory"
        assert LEGACY_COLLECTIONS["code"] == "jarvis_code"

class TestLegacyCopyPlan:
    def test_jarvis_varsa_uryx_hedefe_kopya_planlanir(self) -> None:
        specs = legacy_copy_specs(
            {"jarvis_memory", "jarvis_documents"},
            {
                "memory": "uryx_memory",
                "documents": "uryx_documents",
                "conversations": "uryx_conversations",
                "code": "uryx_code",
            },
        )
        pairs = {(item.source, item.target) for item in specs}
        assert ("jarvis_memory", "uryx_memory") in pairs
        assert ("jarvis_documents", "uryx_documents") in pairs
        assert all(item.source.startswith("jarvis_") for item in specs)

    def test_kaynak_yoksa_plan_bos(self) -> None:
        assert (
            legacy_copy_specs(
                {"uryx_memory"},
                {"memory": "uryx_memory"},
            )
            == []
        )

    def test_hedef_zaten_jarvis_ise_kopyalama(self) -> None:
        assert (
            legacy_copy_specs(
                {"jarvis_memory"},
                {"memory": "jarvis_memory"},
            )
            == []
        )

class TestCopyDimensionGuard:
    def test_384_nokta_kalir_1024_atlanir(self) -> None:
        kept = filter_copy_points(
            [
                {"id": "a", "vector": [0.1] * 384, "payload": {"k": 1}},
                {"id": "b", "vector": [0.1] * 1024, "payload": {"k": 2}},
            ],
            dimension=384,
        )
        assert [row["id"] for row in kept] == ["a"]

class TestCopyDoesNotWipe:
    async def test_kopya_ayni_id_jarvis_silinmez(self) -> None:
        from app.services.rag.vector_store import QdrantVectorStore

        settings = Settings(
            embedding_dim=384,
            qdrant_collection_memory="uryx_memory",
            qdrant_collection_documents="uryx_documents",
            qdrant_collection_conversations="uryx_conversations",
            qdrant_collection_code="uryx_code",
        )
        store = QdrantVectorStore(settings)
        store._dimension = 384
        fake = _FakeQdrant()
        fake.seed(
            "jarvis_memory",
            point_id="11111111-1111-1111-1111-111111111111",
            source_id="mem-1",
            vector=[0.2] * 384,
            payload={"content": "RTX 5070"},
        )
        store._client = fake  # type: ignore[assignment]
        store.available = True

        report = await store.copy_legacy_collections()
        assert fake.delete_collection_calls == []
        assert "jarvis_memory" in fake.points
        assert "uryx_memory" in fake.points
        dest = fake.points["uryx_memory"]
        assert "11111111-1111-1111-1111-111111111111" in dest
        assert dest["11111111-1111-1111-1111-111111111111"]["payload"]["_source_id"] == "mem-1"
        assert report["memory"].source_count == 1
        assert report["memory"].target_count == 1

    async def test_ensure_384_cosine_recreate_yok(self) -> None:
        from app.services.rag.vector_store import QdrantVectorStore
        from qdrant_client import models

        settings = Settings(
            embedding_dim=384,
            qdrant_collection_memory="uryx_memory",
            qdrant_collection_documents="uryx_documents",
            qdrant_collection_conversations="uryx_conversations",
            qdrant_collection_code="uryx_code",
        )
        store = QdrantVectorStore(settings)
        store._dimension = 384
        fake = _FakeQdrant()
        store._client = fake  # type: ignore[assignment]
        await store.ensure_collections()
        created = fake.created["uryx_memory"]
        assert created["size"] == 384
        assert created["distance"] == models.Distance.COSINE
        assert fake.delete_collection_calls == []

class _FakeQdrant:
    def __init__(self) -> None:
        self.points: dict[str, dict[str, dict]] = {}
        self.created: dict[str, dict] = {}
        self.delete_collection_calls: list[str] = []

    def seed(
        self,
        collection: str,
        *,
        point_id: str,
        source_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        bucket = self.points.setdefault(collection, {})
        bucket[point_id] = {
            "vector": vector,
            "payload": {**payload, "_source_id": source_id},
        }

    async def get_collections(self) -> SimpleNamespace:
        names = set(self.points) | set(self.created)
        return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in names])

    async def create_collection(self, collection_name: str, vectors_config, **kwargs) -> None:
        self.created[collection_name] = {
            "size": vectors_config.size,
            "distance": vectors_config.distance,
        }
        self.points.setdefault(collection_name, {})

    async def scroll(
        self,
        collection_name: str,
        limit: int = 64,
        offset=None,
        with_payload: bool = True,
        with_vectors: bool = True,
    ):
        items = list(self.points.get(collection_name, {}).items())
        start = int(offset or 0)
        chunk = items[start : start + limit]
        records = []
        for pid, body in chunk:
            records.append(
                SimpleNamespace(id=pid, payload=body["payload"], vector=body["vector"])
            )
        nxt = start + limit if start + limit < len(items) else None
        return records, nxt

    async def upsert(self, collection_name: str, points, wait: bool = True) -> None:
        bucket = self.points.setdefault(collection_name, {})
        for point in points:
            payload = dict(point.payload or {})
            bucket[str(point.id)] = {"vector": list(point.vector), "payload": payload}

    async def count(self, collection_name: str, exact: bool = False):
        return SimpleNamespace(count=len(self.points.get(collection_name, {})))

    async def delete_collection(self, name: str) -> None:
        self.delete_collection_calls.append(name)
        self.points.pop(name, None)
