"""Qdrant collection adları: varsayılan ``uryx_*``, eski ``jarvis_*`` kopyalanır.

Volume ``jarvis-*-data`` silinmez. ``recreate()`` ve ``down -v`` yok.
Boyut MiniLM 384 cosine (D9); 1024 vektör kopyalanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

LEGACY_COLLECTIONS: dict[str, str] = {
    "memory": "jarvis_memory",
    "documents": "jarvis_documents",
    "conversations": "jarvis_conversations",
    "code": "jarvis_code",
}

@dataclass(frozen=True, slots=True)
class CopySpec:
    """Bir mantıksal collection için kaynak → hedef kopya."""

    logical: str
    source: str
    target: str

@dataclass(frozen=True, slots=True)
class CopyReport:
    """Kopya sonrası nokta sayıları (kaynak silinmez)."""

    source_count: int
    target_count: int

def legacy_copy_specs(existing: set[str], targets: dict[str, str]) -> list[CopySpec]:
    """Qdrant'ta duran ``jarvis_*`` kaynaklarını ``uryx_*`` hedeflerine eşler."""
    specs: list[CopySpec] = []
    for logical, target in targets.items():
        source = LEGACY_COLLECTIONS.get(logical)
        if not source or source == target:
            continue
        if source not in existing:
            continue
        specs.append(CopySpec(logical=logical, source=source, target=target))
    return specs

def filter_copy_points(
    points: list[dict],
    *,
    dimension: int,
) -> list[dict]:
    """Hedef boyuta uymayan vektörleri at (384 collection'a 1024 yok)."""
    kept: list[dict] = []
    for row in points:
        vector = row.get("vector") or []
        if len(vector) == dimension:
            kept.append(row)
    return kept
