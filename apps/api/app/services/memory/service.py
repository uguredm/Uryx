"""Hafıza servisi — kısa süreli ve uzun süreli hafıza yönetimi.

*Kısa süreli hafıza*: aktif konuşmanın son mesajları, son araç çağrıları ve
aktif belge bağlamı; ``ShortTermMemory`` içinde süreç belleğinde tutulur.

*Uzun süreli hafıza*: PostgreSQL (kaynak doğruluk) + Qdrant (semantik arama)
ikilisi üzerinde saklanan kalıcı kayıtlar.
"""

from __future__ import annotations

import builtins
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Memory, MemoryCategory
from app.db.repositories.conversation import ConversationRepository, MessageRepository
from app.db.repositories.memory import MemoryRepository
from app.db.session import Database
from app.schemas.chat import MemoryRef
from app.services.memory.episodes import summarize_turns
from app.services.memory.evaluator import EvaluationOutcome, MemoryEvaluator
from app.services.memory.ranking import (
    adjust_recency,
    entity_overlap,
    diversify_memory_hits,
    extract_entities,
    normalize_fused,
    rank_memory,
    recency_score,
    score_episode,
    temporal_intent,
)
from app.services.rag.embeddings import SentenceTransformerProvider
from app.services.rag.retriever import reciprocal_rank_fusion
from app.services.rag.vector_store import QdrantVectorStore

logger = get_logger(__name__)

MEMORY_COLLECTION = "memory"
CONVERSATION_COLLECTION = "conversations"

@dataclass(slots=True)
class ShortTermEntry:
    """Kısa süreli hafızadaki tek kayıt."""

    role: str
    content: str

@dataclass(slots=True)
class ShortTermState:
    """Bir sohbetin kısa süreli durumu."""

    messages: deque[ShortTermEntry] = field(default_factory=lambda: deque(maxlen=20))
    recent_tools: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=10))
    active_task: str | None = None
    active_documents: list[str] = field(default_factory=list)

class ShortTermMemory:
    """Sohbet bazlı kısa süreli hafıza (süreç belleği)."""

    def __init__(self, window: int = 20) -> None:
        self._window = window
        self._states: dict[str, ShortTermState] = defaultdict(ShortTermState)

    def state(self, conversation_id: str) -> ShortTermState:
        """Sohbetin durumunu döndürür (yoksa oluşturur)."""
        return self._states[conversation_id]

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        """Mesajı pencereye ekler."""
        self.state(conversation_id).messages.append(ShortTermEntry(role=role, content=content))

    def add_tool_call(self, conversation_id: str, payload: dict[str, Any]) -> None:
        """Son araç çağrılarına ekler."""
        self.state(conversation_id).recent_tools.append(payload)

    def set_active_task(self, conversation_id: str, task: str | None) -> None:
        """Aktif görevi günceller."""
        self.state(conversation_id).active_task = task

    def set_active_documents(self, conversation_id: str, document_ids: list[str]) -> None:
        """Aktif belge bağlamını günceller."""
        self.state(conversation_id).active_documents = document_ids[:10]

    def context_summary(self, conversation_id: str) -> str | None:
        """Sistem promptuna eklenecek kısa özet."""
        state = self._states.get(conversation_id)
        if state is None:
            return None
        parts: list[str] = []
        if state.active_task:
            parts.append(f"Aktif görev: {state.active_task}")
        if state.recent_tools:
            names = ", ".join(t.get("tool_name", "?") for t in list(state.recent_tools)[-3:])
            parts.append(f"Son çalıştırılan araçlar: {names}")
        if state.active_documents:
            parts.append(f"Aktif belge sayısı: {len(state.active_documents)}")
        return "\n".join(parts) if parts else None

    def clear(self, conversation_id: str) -> None:
        """Sohbetin kısa süreli hafızasını temizler."""
        self._states.pop(conversation_id, None)

class MemoryService:
    """Uzun süreli hafıza iş mantığı."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        vector_store: QdrantVectorStore,
        embeddings: SentenceTransformerProvider,
        evaluator: MemoryEvaluator,
    ) -> None:
        self._settings = settings
        self._db = database
        self._vectors = vector_store
        self._embeddings = embeddings
        self._evaluator = evaluator
        self.short_term = ShortTermMemory()

    async def create(
        self,
        content: str,
        *,
        category: MemoryCategory = MemoryCategory.OTHER,
        importance: float = 0.6,
        pinned: bool = False,
        tags: list[str] | None = None,
        source: str = "manual",
        source_conversation_id: str | None = None,
    ) -> Memory:
        """Yeni hafıza kaydı oluşturur ve vektörünü yazar."""
        async with self._db.session() as session:
            repo = MemoryRepository(session)
            existing = await repo.find_similar_text(content)
            if existing is not None and existing.content.strip() == content.strip():
                return existing
        near = await self._find_semantic_duplicate(content)
        if near is not None:
            return near
        async with self._db.session() as session:
            repo = MemoryRepository(session)
            memory = await repo.create(
                content,
                category=category,
                importance=importance,
                pinned=pinned,
                tags=tags,
                source=source,
                source_conversation_id=source_conversation_id,
            )
            await session.refresh(memory)
            snapshot = _snapshot(memory)

        await self._index_vector(snapshot)
        logger.info("memory_created", memory_id=snapshot["id"], category=snapshot["category"])
        return memory

    async def update(self, memory_id: str, **values: Any) -> Memory:
        """Hafıza kaydını günceller."""
        async with self._db.session() as session:
            repo = MemoryRepository(session)
            memory = await repo.get(memory_id)
            if memory is None:
                raise NotFoundError("Hafıza kaydı bulunamadı.")
            await repo.update(memory, **{k: v for k, v in values.items() if v is not None})
            await session.refresh(memory)
            snapshot = _snapshot(memory)

        if values.get("content"):
            await self._index_vector(snapshot)
        return memory

    async def set_pinned(self, memory_id: str, pinned: bool) -> None:
        """Kaydı sabitler / sabiti kaldırır."""
        async with self._db.session() as session:
            await MemoryRepository(session).set_pinned(memory_id, pinned)

    async def delete(self, memory_id: str) -> bool:
        """Kaydı siler (DB + vektör)."""
        async with self._db.session() as session:
            repo = MemoryRepository(session)
            if await repo.get(memory_id) is None:
                return False
            await repo.delete(memory_id)
        await self._vectors.delete(MEMORY_COLLECTION, [memory_id])
        return True

    async def list(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        category: MemoryCategory | None = None,
        query: str | None = None,
    ) -> list[Memory]:
        """Aktif hafıza kayıtlarını listeler."""
        async with self._db.session() as session:
            return await MemoryRepository(session).list_active(
                limit=limit, offset=offset, category=category, query=query
            )

    async def stats(self) -> dict[str, Any]:
        """Hafıza istatistikleri."""
        async with self._db.session() as session:
            return await MemoryRepository(session).stats()

    async def recall(self, query: str, *, top_k: int | None = None) -> builtins.list[MemoryRef]:
        """Sorguyla ilgili hafıza kayıtlarını getirir.

        Mem0: dense (Qdrant) + kelime (Postgres) → RRF → önem/tazelik.
        Letta: boş kalan yuvalara sohbet bölüm özetleri eklenir.
        """
        top_k = top_k or self._settings.memory_top_k
        if not self._db.available:
            return []

        refs: list[MemoryRef] = []
        seen: set[str] = set()

        async with self._db.session() as session:
            repo = MemoryRepository(session)
            for pinned_memory in await repo.list_pinned(limit=max(1, top_k // 2)):
                seen.add(pinned_memory.id)
                refs.append(
                    MemoryRef(
                        id=pinned_memory.id,
                        content=pinned_memory.content,
                        category=_category_value(pinned_memory.category),
                        score=1.0,
                    )
                )
            for core in await repo.list_core(
                limit=self._settings.memory_core_slots,
                min_importance=self._settings.memory_core_min_importance,
            ):
                if core.id in seen or len(refs) >= top_k:
                    continue
                seen.add(core.id)
                refs.append(
                    MemoryRef(
                        id=core.id,
                        content=core.content,
                        category=_category_value(core.category),
                        score=0.94,
                    )
                )

        remaining = max(0, top_k - len(refs))
        if remaining and query.strip():
            ranked = await self._hybrid_memory_hits(query, remaining + len(seen))
            ranked = [(mid, score) for mid, score in ranked if mid not in seen]
            if ranked:
                async with self._db.session() as session:
                    memories_by_id = {
                        m.id: m
                        for m in await MemoryRepository(session).get_many([h[0] for h in ranked])
                    }
                pool = [
                    (memory_id, memories_by_id[memory_id].content, score)
                    for memory_id, score in ranked
                    if memory_id in memories_by_id
                ]
                for memory_id, score in diversify_memory_hits(pool, remaining):
                    recalled_memory = memories_by_id.get(memory_id)
                    if recalled_memory is None:
                        continue
                    seen.add(memory_id)
                    refs.append(
                        MemoryRef(
                            id=recalled_memory.id,
                            content=recalled_memory.content,
                            category=_category_value(recalled_memory.category),
                            score=score,
                        )
                    )

        leftover = max(0, top_k - len(refs))
        if leftover and query.strip() and self._settings.memory_episode_enabled:
            for episode in await self._recall_episodes(query, leftover, seen):
                refs.append(episode)

        if refs:
            memory_ids = [r.id for r in refs if r.category != "conversation"]
            if memory_ids:
                async with self._db.session() as session:
                    await MemoryRepository(session).mark_used(memory_ids)
        return refs[:top_k]

    async def search(self, query: str, top_k: int = 5) -> builtins.list[MemoryRef]:
        """Yalnızca semantik arama (sabitlenmişleri öne almadan)."""
        if not self._vectors.available or not self._db.available:
            fallback_memories = await self.list(limit=top_k, query=query)
            return [
                MemoryRef(
                    id=m.id,
                    content=m.content,
                    category=_category_value(m.category),
                    score=0.5,
                )
                for m in fallback_memories
            ]
        vector = await self._embeddings.embed_query(query)
        hits = await self._vectors.search(MEMORY_COLLECTION, vector=vector, limit=top_k)
        async with self._db.session() as session:
            memories_by_id = {
                m.id: m for m in await MemoryRepository(session).get_many([h.id for h in hits])
            }
        return [
            MemoryRef(
                id=hit.id,
                content=memories_by_id[hit.id].content,
                category=_category_value(memories_by_id[hit.id].category),
                score=round(hit.score, 4),
            )
            for hit in hits
            if hit.id in memories_by_id
        ]

    async def evaluate_and_store(
        self, user_message: str, assistant_message: str, *, conversation_id: str | None
    ) -> builtins.list[Memory]:
        """Konuşmayı değerlendirir ve uygun bilgileri kaydeder."""
        if not self._db.available:
            return []

        created: builtins.list[Memory] = []
        if self._settings.memory_auto_enabled:
            outcome: EvaluationOutcome = await self._evaluator.evaluate(
                user_message, assistant_message
            )
            if not outcome.should_save:
                logger.debug("memory_not_saved", reason=outcome.reason)
            else:
                for candidate in outcome.candidates:
                    async with self._db.session() as session:
                        duplicate = await MemoryRepository(session).find_similar_text(
                            candidate.content
                        )
                    if duplicate is not None:
                        logger.debug("memory_duplicate_skipped")
                        continue
                    memory = await self.create(
                        candidate.content,
                        category=candidate.category,
                        importance=candidate.importance,
                        tags=candidate.tags,
                        source="auto",
                        source_conversation_id=conversation_id,
                    )
                    created.append(memory)
        if conversation_id:
            await self._safe_index_episode(conversation_id)
        return created

    async def index_episode(self, conversation_id: str) -> str | None:
        """Sohbeti çıkarımsal özetleyip ``jarvis_conversations`` koleksiyonuna yazar."""
        if not self._settings.memory_episode_enabled or not self._db.available:
            return None
        async with self._db.session() as session:
            records = await MessageRepository(session).last_n(conversation_id, 24)
            conversation = await ConversationRepository(session).get(conversation_id)
            title = conversation.title if conversation is not None else "Sohbet"
            turns = [
                (_role_name(record.role), record.content)
                for record in records
                if record.content and _role_name(record.role) in {"user", "assistant"}
            ]
            summary = await summarize_turns(turns, self._evaluator.llm)
            if not summary:
                return None
            await ConversationRepository(session).set_summary(conversation_id, summary)

        if self._vectors.available:
            vector = await self._embeddings.embed_query(f"{title}\n{summary}")
            await self._vectors.upsert(
                CONVERSATION_COLLECTION,
                ids=[conversation_id],
                vectors=[vector],
                payloads=[
                    {
                        "content": summary[:2000],
                        "title": title,
                        "conversation_id": conversation_id,
                    }
                ],
            )
        logger.debug("episode_indexed", conversation_id=conversation_id, chars=len(summary))
        return summary

    async def _safe_index_episode(self, conversation_id: str) -> None:
        """Letta sleeptime: tur kaydetmese bile bölüm özetini yazar."""
        try:
            await self.index_episode(conversation_id)
        except Exception as exc:
            logger.warning("episode_index_failed", error=str(exc))

    async def _hybrid_memory_hits(self, query: str, limit: int) -> list[tuple[str, float]]:
        """Dense + sparse RRF, sonra önem/tazelik (Mem0)."""
        dense: list[tuple[str, float]] = []
        if self._vectors.available:
            vector = await self._embeddings.embed_query(query)
            results = await self._vectors.search(
                MEMORY_COLLECTION,
                vector=vector,
                limit=limit,
                score_threshold=self._settings.memory_min_score,
            )
            dense = [(hit.id, hit.score) for hit in results]

        sparse: list[tuple[str, float]] = []
        async with self._db.session() as session:
            sparse = await MemoryRepository(session).sparse_search(query, limit=limit)

        if not dense and not sparse:
            return []

        fused = reciprocal_rank_fusion(dense, sparse)
        peak = max(fused.values(), default=0.0)
        ids = list(fused)
        entities = extract_entities(query)
        intent = temporal_intent(query)
        async with self._db.session() as session:
            memories = {m.id: m for m in await MemoryRepository(session).get_many(ids)}

        ranked: list[tuple[str, float]] = []
        for memory_id, raw in fused.items():
            memory = memories.get(memory_id)
            if memory is None:
                continue
            when = memory.last_used_at or memory.created_at
            score = rank_memory(
                normalize_fused(raw, peak),
                memory.importance,
                adjust_recency(
                    recency_score(
                        when, half_life_days=self._settings.memory_recency_half_life_days
                    ),
                    intent,
                ),
                pinned=memory.pinned,
                entity=entity_overlap(entities, memory.content),
            )
            if score < self._settings.memory_min_score and memory_id not in {h[0] for h in dense}:
                continue
            ranked.append((memory_id, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:limit]

    async def _recall_episodes(
        self, query: str, limit: int, seen: set[str]
    ) -> list[MemoryRef]:
        """Qdrant arşivi, sonra Postgres özet yedeği (Letta + AnythingLLM backfill)."""
        refs: list[MemoryRef] = []
        if self._vectors.available:
            vector = await self._embeddings.embed_query(query)
            hits = await self._vectors.search(
                CONVERSATION_COLLECTION,
                vector=vector,
                limit=limit + len(seen),
                score_threshold=self._settings.memory_min_score,
            )
            for hit in hits:
                if hit.id in seen:
                    continue
                content = str(hit.payload.get("content") or "").strip()
                if not content:
                    continue
                seen.add(hit.id)
                refs.append(
                    MemoryRef(
                        id=hit.id,
                        content=content,
                        category="conversation",
                        score=round(hit.score, 4),
                    )
                )
                if len(refs) >= limit:
                    return refs

        leftover = max(0, limit - len(refs))
        if leftover:
            refs.extend(await self._recall_episode_summaries(query, leftover, seen))
        return refs[:limit]

    async def _recall_episode_summaries(
        self, query: str, limit: int, seen: set[str]
    ) -> list[MemoryRef]:
        """``list_with_summaries`` + Mem0 varlık/kelime skoru. LIKE araması değil."""
        async with self._db.session() as session:
            conversations = await ConversationRepository(session).list_with_summaries(
                limit=40
            )
        entities = extract_entities(query)
        scored: list[tuple[str, str, float]] = []
        for conversation in conversations:
            if conversation.id in seen:
                continue
            summary = (conversation.summary or "").strip()
            if not summary:
                continue
            score = score_episode(query, summary, entities)
            if score <= 0:
                continue
            scored.append((conversation.id, summary, score))
        scored.sort(key=lambda item: item[2], reverse=True)
        refs: list[MemoryRef] = []
        for conversation_id, summary, score in scored[:limit]:
            seen.add(conversation_id)
            refs.append(
                MemoryRef(
                    id=conversation_id,
                    content=summary,
                    category="conversation",
                    score=round(0.35 + 0.45 * score, 4),
                )
            )
        return refs

    async def _find_semantic_duplicate(self, content: str) -> Memory | None:
        """Mem0 hash/vektör yinelenmesini yakalar (yalnızca gerçek embedding)."""
        if (
            not self._vectors.available
            or self._embeddings.using_fallback
            or not self._db.available
        ):
            return None
        vector = await self._embeddings.embed_query(content)
        hits = await self._vectors.search(
            MEMORY_COLLECTION,
            vector=vector,
            limit=1,
            score_threshold=self._settings.memory_semantic_dedup_score,
        )
        if not hits:
            return None
        async with self._db.session() as session:
            return await MemoryRepository(session).get(hits[0].id)

    async def _index_vector(self, snapshot: dict[str, Any]) -> None:
        """Hafıza kaydının vektörünü Qdrant'a yazar."""
        if not self._vectors.available:
            return
        vector = await self._embeddings.embed_query(snapshot["content"])
        await self._vectors.upsert(
            MEMORY_COLLECTION,
            ids=[snapshot["id"]],
            vectors=[vector],
            payloads=[
                {
                    "content": snapshot["content"][:2000],
                    "category": snapshot["category"],
                    "importance": snapshot["importance"],
                    "pinned": snapshot["pinned"],
                }
            ],
        )

    async def reindex_all(self) -> int:
        """Tüm aktif hafıza kayıtlarının vektörlerini yeniden üretir."""
        if not self._vectors.available or not self._db.available:
            return 0
        async with self._db.session() as session:
            memories = await MemoryRepository(session).list_active(limit=5000)
            snapshots = [_snapshot(m) for m in memories]
        if not snapshots:
            return 0
        vectors = await self._embeddings.embed([s["content"] for s in snapshots])
        return await self._vectors.upsert(
            MEMORY_COLLECTION,
            ids=[s["id"] for s in snapshots],
            vectors=vectors,
            payloads=[
                {
                    "content": s["content"][:2000],
                    "category": s["category"],
                    "importance": s["importance"],
                    "pinned": s["pinned"],
                }
                for s in snapshots
            ],
        )

def _role_name(role: Any) -> str:
    """Mesaj rolünü string'e indirger."""
    return str(role.value if hasattr(role, "value") else role)

def _category_value(category: Any) -> str:
    """Enum veya string kategoriyi string'e indirger."""
    return str(category.value if hasattr(category, "value") else category)

def _snapshot(memory: Memory) -> dict[str, Any]:
    """ORM nesnesinden oturumdan bağımsız anlık görüntü çıkarır."""
    return {
        "id": memory.id,
        "content": memory.content,
        "category": _category_value(memory.category),
        "importance": memory.importance,
        "pinned": memory.pinned,
    }
