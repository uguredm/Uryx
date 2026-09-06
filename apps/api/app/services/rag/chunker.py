"""Metin parçalama (chunking).

Doğal sınırları korumaya çalışan özyinelemeli bir bölücü: önce paragraf, sonra
satır, sonra cümle, en son karakter sınırı. Kodda dil ayırıcıları (class/def)
sonra satır; cümle yok.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.services.rag.parsers import ParsedDocument

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9])")

_ATX_HEADER = re.compile(r"^#{1,6}[ \t]+\S")

_CODE_SEPARATORS: dict[str, tuple[str, ...]] = {
    "text/x-python": ("\nclass ", "\ndef ", "\n\tdef ", "\n\n", "\n"),
    "text/javascript": (
        "\nfunction ",
        "\nconst ",
        "\nlet ",
        "\nvar ",
        "\nclass ",
        "\n\n",
        "\n",
    ),
    "text/typescript": (
        "\nenum ",
        "\ninterface ",
        "\nnamespace ",
        "\ntype ",
        "\nfunction ",
        "\nconst ",
        "\nlet ",
        "\nvar ",
        "\nclass ",
        "\n\n",
        "\n",
    ),
    "text/x-go": ("\nfunc ", "\nvar ", "\nconst ", "\ntype ", "\n\n", "\n"),
}

_CODE_DECL_PREFIXES = (
    "class ",
    "def ",
    "function ",
    "func ",
    "const ",
    "let ",
    "var ",
    "enum ",
    "interface ",
    "namespace ",
    "type ",
)

@dataclass(slots=True)
class Chunk:
    """Vektörleştirilecek metin parçası."""

    id: str
    index: int
    content: str
    page: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Repository'ye uygun sözlük."""
        return {"id": self.id, "index": self.index, "content": self.content, "page": self.page}

def split_markdown_headers(text: str) -> list[str]:
    """LangChain: ATX başlıkta yeni bölüm; başlık içerikte kalır (strip_headers=False).

    Çit (```) içindeki ``#`` satırları bölüm açmaz.
    """
    if not text.strip():
        return []
    sections: list[list[str]] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and _ATX_HEADER.match(stripped) and current:
            sections.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        sections.append(current)
    return ["\n".join(block).strip() for block in sections if "\n".join(block).strip()]

def code_separators(mime: str) -> list[str] | None:
    """LangChain dil ayırıcıları; bilinmeyen mime → None (satır bölme)."""
    found = _CODE_SEPARATORS.get(mime)
    return list(found) if found else None

def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
    is_code: bool = False,
    min_chars: int = 180,
    is_markdown: bool = False,
    mime: str = "",
) -> list[str]:
    """Metni örtüşmeli parçalara böler.

    Args:
        text: Bölünecek metin.
        chunk_size: Hedef parça uzunluğu (karakter).
        overlap: Ardışık parçalar arası örtüşme (karakter).
        is_code: Kod dosyası ise cümle bölme uygulanmaz.
        is_markdown: ATX başlıklarda önce bölüm ayır (LangChain).
        mime: Kod dil ayırıcıları için (``text/x-python`` …).

    Returns:
        Boş olmayan parça listesi.
    """
    text = text.strip()
    if not text:
        return []
    if is_markdown and not is_code:
        sections = split_markdown_headers(text)
        if len(sections) > 1:
            pieces: list[str] = []
            for section in sections:
                pieces.extend(
                    chunk_text(
                        section,
                        chunk_size=chunk_size,
                        overlap=overlap,
                        is_code=False,
                        min_chars=min_chars,
                        is_markdown=False,
                        mime=mime,
                    )
                )
            return pieces
    if len(text) <= chunk_size:
        return [text]

    overlap = max(0, min(overlap, chunk_size // 2))
    language_seps = is_code and code_separators(mime)
    if is_code:
        separators = language_seps or ["\n\n", "\n"]
    else:
        separators = ["\n\n", "\n", ". "]
    units = _split_recursive(text, separators, chunk_size)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif language_seps and _is_code_decl(unit):
            chunks.append(current.strip())
            current = (_overlap_prefix(current, overlap) + "\n" + unit).strip() if overlap else unit
        elif len(current) + len(unit) + 1 <= chunk_size:
            current = f"{current}\n{unit}" if not current.endswith("\n") else current + unit
        else:
            chunks.append(current.strip())
            current = (_overlap_prefix(current, overlap) + "\n" + unit).strip() if overlap else unit
    if current.strip():
        chunks.append(current.strip())

    return _merge_small([c for c in chunks if c.strip()], min_chars)

def _split_recursive(text: str, separators: list[str], limit: int) -> list[str]:
    """Metni ayırıcılar boyunca limitin altına inene kadar böler."""
    if len(text) <= limit:
        return [text]
    if not separators:
        return [text[i : i + limit] for i in range(0, len(text), limit)]

    separator, *rest = separators
    parts = _split_units(text, separator)

    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        out.extend(_split_recursive(part, rest, limit) if len(part) > limit else [part])
    return out

def _is_code_decl(unit: str) -> bool:
    """LangChain dil ayırıcısından gelen sınıf/fonksiyon birimi."""
    return unit.lstrip().startswith(_CODE_DECL_PREFIXES)

def _split_units(text: str, separator: str) -> list[str]:
    """Ayırıcıda böl; ``\\ndef `` gibi yapısal ayırıcıyı sonraki parçada tut."""
    if separator == ". ":
        return _SENTENCE_SPLIT.split(text)
    parts = text.split(separator)
    if len(parts) <= 1:
        return parts
    lead = separator.lstrip("\n")
    if not lead or separator in {"\n", "\n\n"}:
        return parts
    return [parts[0], *(lead + part for part in parts[1:])]

def _merge_small(chunks: list[str], min_chars: int) -> list[str]:
    """Open WebUI ``Chunk Min Size Target``: cılız parçaları komşuya yapıştırır."""
    if min_chars <= 0 or len(chunks) < 2:
        return chunks
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] = f"{merged[-1]}\n{chunk}"
        else:
            merged.append(chunk)
    if len(merged) >= 2 and len(merged[-1]) < min_chars:
        merged[-2] = f"{merged[-2]}\n{merged[-1]}"
        merged.pop()
    return merged

def _overlap_prefix(previous: str, size: int) -> str:
    """Chonkie OverlapRefinery prefix: önceki parçanın sonundan cümle/paragraf.

    Tokenizer yok (character). ``justified`` / token modu yok. Tek cümle
    ``size``'ı aşıyorsa ``_tail`` (kelime sınırı).
    """
    if size <= 0 or not previous.strip():
        return ""
    text = previous.strip()
    if len(text) <= size:
        return text
    for separator, joiner in (("\n\n", "\n\n"), ("\n", "\n"), (". ", " ")):
        parts = _overlap_parts(text, separator)
        if len(parts) < 2:
            continue
        taken: list[str] = []
        total = 0
        for part in reversed(parts):
            extra = len(part) + (len(joiner) if taken else 0)
            if not taken and len(part) > size:
                break
            if taken and total + extra > size:
                break
            taken.append(part)
            total += extra
        if taken:
            taken.reverse()
            return joiner.join(taken)
    return _tail(text, size)

def _overlap_parts(text: str, separator: str) -> list[str]:
    """Örtüşme için ayırıcıda böl; boş parçaları at."""
    raw = _SENTENCE_SPLIT.split(text) if separator == ". " else text.split(separator)
    return [part.strip() for part in raw if part.strip()]

def _tail(text: str, size: int) -> str:
    """Örtüşme için metnin sonundan kelime sınırına saygılı bir parça alır."""
    if size <= 0 or len(text) <= size:
        return text
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < size // 2 else tail

def chunk_document(
    parsed: ParsedDocument,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
    min_chars: int = 180,
) -> list[Chunk]:
    """Ayrıştırılmış belgeyi sayfa bilgisini koruyarak parçalar."""
    is_code = parsed.collection == "code"
    is_markdown = parsed.mime_type in {"text/markdown", "text/html"}
    chunks: list[Chunk] = []
    index = 0
    for page in parsed.pages:
        for piece in chunk_text(
            page.text,
            chunk_size=chunk_size,
            overlap=overlap,
            is_code=is_code,
            min_chars=min_chars,
            is_markdown=is_markdown,
            mime=parsed.mime_type,
        ):
            chunks.append(Chunk(id=str(uuid.uuid4()), index=index, content=piece, page=page.page))
            index += 1
    return chunks
