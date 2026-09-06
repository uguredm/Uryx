"""Embedding sağlayıcıları.

Varsayılan sağlayıcı çok dilli (Türkçe destekli) bir MiniLM modelini **CPU**
üzerinde çalıştırır; GPU tercihen LLM'e bırakılır. Model indirilemezse
deterministik bir hash-embedding fallback'i devreye girer: RAG kalitesi düşer
ama sistem ayakta kalır (bkz. README — Fallback Matrisi).
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@runtime_checkable
class EmbeddingProvider(Protocol):
    """Embedding üretici sözleşmesi."""

    @property
    def dimension(self) -> int:
        """Vektör boyutu."""
        ...

    @property
    def model_name(self) -> str:
        """Model kimliği."""
        ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Metinleri vektöre çevirir."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Tek sorguyu vektöre çevirir."""
        ...

class HashEmbeddingProvider:
    """Deterministik yedek embedding.

    Karakter n-gram'larını sabit boyutlu bir vektöre hash'ler. Semantik değildir
    ancak birebir/yakın eşleşmelerde çalışır ve model indirilemediğinde sistemin
    çalışmaya devam etmesini sağlar.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        """Vektör boyutu."""
        return self._dimension

    @property
    def model_name(self) -> str:
        """Model kimliği."""
        return "hash-fallback"

    def _vectorize(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        normalized = " ".join(text.lower().split())
        if not normalized:
            return vector
        tokens = normalized.split()
        grams = list(tokens)
        for token in tokens:
            grams.extend(token[i : i + 3] for i in range(max(len(token) - 2, 1)))
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Metinleri vektöre çevirir."""
        return [self._vectorize(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        """Tek sorguyu vektöre çevirir."""
        return self._vectorize(text)

class SentenceTransformerProvider:
    """``sentence-transformers`` tabanlı çok dilli embedding sağlayıcısı."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: object | None = None
        self._dimension = settings.embedding_dim
        self._fallback = HashEmbeddingProvider(settings.embedding_dim)
        self._using_fallback = False
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        """Vektör boyutu."""
        return self._dimension

    @property
    def model_name(self) -> str:
        """Aktif model kimliği."""
        return self._fallback.model_name if self._using_fallback else self._settings.embedding_model

    @property
    def using_fallback(self) -> bool:
        """Hash fallback'i aktif mi?"""
        return self._using_fallback

    async def load(self) -> None:
        """Modeli arka planda yükler; başarısız olursa fallback'e düşer."""
        async with self._lock:
            if self._model is not None or self._using_fallback:
                return
            try:
                self._model = await asyncio.to_thread(self._load_sync)
                dim = int(self._model.get_sentence_embedding_dimension())  # type: ignore[attr-defined]
                if dim != self._dimension:
                    logger.warning("embedding_dim_mismatch", configured=self._dimension, actual=dim)
                    self._dimension = dim
                logger.info(
                    "embedding_model_loaded",
                    model=self._settings.embedding_model,
                    dim=self._dimension,
                    device=self._settings.embedding_device,
                )
            except Exception as exc:
                self._using_fallback = True
                logger.warning(
                    "embedding_model_failed_using_fallback",
                    model=self._settings.embedding_model,
                    error=str(exc),
                )

    def _load_sync(self) -> object:
        """Modeli senkron yükler (thread içinde çağrılır)."""
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(
            self._settings.embedding_model,
            device=self._settings.embedding_device,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Metin listesini vektörleştirir."""
        if not texts:
            return []
        await self.load()
        if self._using_fallback or self._model is None:
            return await self._fallback.embed(texts)
        try:
            return await asyncio.to_thread(self._encode_sync, list(texts))
        except Exception as exc:
            logger.error("embedding_failed", error=str(exc))
            return await self._fallback.embed(texts)

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Senkron encode (thread içinde)."""
        vectors = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=self._settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(x) for x in row] for row in vectors]

    async def embed_query(self, text: str) -> list[float]:
        """Tek sorguyu vektörleştirir."""
        result = await self.embed([text])
        return result[0] if result else [0.0] * self._dimension

def create_embedding_provider(settings: Settings) -> SentenceTransformerProvider:
    """Ayarlara göre embedding sağlayıcısı üretir."""
    return SentenceTransformerProvider(settings)
