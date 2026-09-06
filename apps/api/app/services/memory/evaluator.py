"""Memory evaluator.

Her konuşma turundan sonra çalışır ve şu soruyu cevaplar:
*"Bu konuşmadan gelecekte kullanıcıya yardımcı olacak kalıcı bir bilgi
çıkarılabilir mi?"*

Üç katmanlı korumaya sahiptir:

1. **Ön filtre** — LLM'i hiç çağırmadan önemsiz turları eler (selamlaşma,
   çok kısa mesajlar, tek seferlik istekler).
2. **Hassas veri filtresi** — şifre, token, API key, kart/kimlik numarası
   içeren adayları reddeder.
3. **Kalıcılık filtresi** — küçük modellerin ürettiği üç tip çöpü eler:
   asistanın kendi hakkında yazdığı "hafızama kaydedildi" cümleleri, tek
   seferlik komutlar ("son şarkıyı aç") ve kullanıcıyla ilgisi olmayan genel
   ansiklopedi/görüş cümleleri ("yapay zeka için temiz veri gerekir").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.db.models import MemoryCategory
from app.services.llm.base import ChatMessage, LLMClient
from app.services.llm.prompts import MEMORY_EVALUATOR_PROMPT

logger = get_logger(__name__)

SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(?:şifre|sifre|parola|password|passwd|pwd)\w*\s*[:=]?\s*\S+"),
    re.compile(r"(?i)\b(?:api[_\s-]?key|apikey|secret|token|bearer|auth)\w*\s*[:=]?\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    re.compile(r"\b\d{11}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

TRIVIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^(selam|merhaba|günaydın|gunaydin|iyi akşamlar|iyi geceler|nasılsın|nasilsin|"
        r"teşekkürler|tesekkurler|sağol|sagol|tamam|ok|okey|peki|evet|hayır|hayir|"
        r"görüşürüz|gorusuruz|hoşça kal|hoscakal)[\s!.?]*$",
        re.IGNORECASE,
    ),
]

EXPLICIT_SAVE_HINTS = re.compile(
    r"(?i)\b(hatırla|hatirla|unutma|not al|aklında tut|aklinda tut|kaydet|"
    r"bunu bil|bilmen(i| ) ?ister|remember)\b"
)

FACT_HINTS = re.compile(
    r"(?i)\b(adım|ismim|benim adım|tercihim|sevdiğim|sevdigim|gpu|rtx|"
    r"klasörüm|klasorum|yaşım|yasim|oturuyorum|çalışıyorum|calisiyorum)\b"
)

SELF_REFERENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)hafıza\w*\s+(?:\S+\s+){0,3}?(?:kayded|yazıl|eklen|aktar)"),
    re.compile(
        r"(?i)\b(?:kaydedildi|kaydettim|not aldım|not ettim|hatırlayacağım|"
        r"akılda tutuldu|unutmayacağım)\b"
    ),
    re.compile(r"(?i)\bbu (?:bilgi|bilgiler|detay|ayrıntı)\w*\b.{0,60}?\b(?:kayded|sakla)"),
]

TRANSIENT_ACTION = re.compile(
    r"(?i)\b(?:aç|kapat|çal|oynat|durdur|getir|göster|başlat|listele|indir|yükle|"
    r"gönder|ara|bul|sil|oluştur|kur|çalıştır|güncelle|incele|tara|düzelt|ekle)"
    r"(?:ma|me)?k?\s*(?:ist(?:iyor|iyorum|edi|erim))?[\s.!]*$"
)

GENERIC_CLAIM = re.compile(
    r"(?i)\b(?:gerekir|gerekebilir|gereklidir|önemlidir|genellikle|çoğu zaman|ideal|"
    r"avantaj\w*|dezavantaj\w*|tavsiye edilir|önerilir|mümkündür|sayılır|kullanılır|"
    r"bilinir|olabilir|belirlendi|tespit edildi|öğrenildi|açıklandı|duyuruldu|"
    r"bildirildi|raporlandı|yayınlandı|görev(?:de|ini)\b)"
)

USER_ANCHOR = re.compile(
    r"(?i)\b(?:kullanıcı\w*|benim|kendi\w*|bilgisayar\w*|makine\w*|sistem\w*|proje\w*|"
    r"uryx\w*|klasör\w*|dizin\w*|repo\w*|gpu|rtx|cpu|ram|windows|linux|"
    r"ad[ıi]m|ismim|ismi|adı)\b"
)

MIN_USER_LENGTH = 8

@dataclass(slots=True)
class MemoryCandidate:
    """Kaydedilmeye aday bilgi."""

    content: str
    category: MemoryCategory
    importance: float
    tags: list[str]

@dataclass(slots=True)
class EvaluationOutcome:
    """Değerlendirme sonucu."""

    should_save: bool
    reason: str
    candidates: list[MemoryCandidate]

class MemoryEvaluator:
    """Konuşmadan kalıcı bilgi çıkaran değerlendirici."""

    def __init__(self, llm: LLMClient, *, max_tokens: int = 512) -> None:
        self._llm = llm
        self._max_tokens = max_tokens

    @property
    def llm(self) -> LLMClient:
        """Bölüm özeti aynı yerel istemciyi kullanır."""
        return self._llm

    @staticmethod
    def is_trivial(user_message: str) -> bool:
        """LLM'e gitmeden elenebilecek bir tur mu?"""
        text = user_message.strip()
        if EXPLICIT_SAVE_HINTS.search(text) or FACT_HINTS.search(text):
            return False
        if len(text) < MIN_USER_LENGTH:
            return True
        return any(pattern.match(text) for pattern in TRIVIAL_PATTERNS)

    @staticmethod
    def contains_sensitive(text: str) -> bool:
        """Metin hassas veri içeriyor mu?"""
        return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)

    @staticmethod
    def is_self_referential(content: str) -> bool:
        """Aday, asistanın kendi kayıt eylemini mi anlatıyor?"""
        return any(pattern.search(content) for pattern in SELF_REFERENTIAL_PATTERNS)

    @classmethod
    def rejection_reason(cls, content: str) -> str | None:
        """Aday kalıcı hafızaya uygun değilse gerekçesini döndürür.

        Küçük modeller sık sık üç tip çöp üretir; hiçbiri gelecekte işe
        yaramadığı için burada elenir.

        Args:
            content: Aday hafıza cümlesi.

        Returns:
            Reddetme gerekçesi veya uygunsa ``None``.
        """
        text = content.strip()
        if cls.is_self_referential(text):
            return "Asistanın kendi kayıt eylemini anlatıyor; bilgi taşımıyor."
        if TRANSIENT_ACTION.search(text):
            return "Tek seferlik komut/istek; bağlamı geçince anlamsız."
        if GENERIC_CLAIM.search(text) and not USER_ANCHOR.search(text):
            return "Kullanıcıya bağlanmayan genel bilgi/görüş cümlesi."
        return None

    async def evaluate(self, user_message: str, assistant_message: str) -> EvaluationOutcome:
        """Konuşma turunu değerlendirir.

        Args:
            user_message: Kullanıcının son mesajı.
            assistant_message: Asistanın cevabı.

        Returns:
            Kaydedilecek adaylar ve gerekçe.
        """
        if self.is_trivial(user_message):
            return EvaluationOutcome(False, "Önemsiz konuşma turu (ön filtre).", [])

        if self.contains_sensitive(user_message):
            return EvaluationOutcome(False, "Mesaj hassas veri içeriyor; kaydedilmedi.", [])

        conversation = (
            f"KULLANICI: {user_message.strip()[:4000]}\n\n"
            f"ASİSTAN: {assistant_message.strip()[:2000]}"
        )
        messages = [
            ChatMessage(role="system", content=MEMORY_EVALUATOR_PROMPT),
            ChatMessage(role="user", content=conversation),
        ]

        try:
            result = await self._llm.complete(
                messages,
                temperature=0.1,
                max_tokens=self._max_tokens,
                enable_thinking=False,
            )
        except Exception as exc:
            logger.warning("memory_evaluator_llm_failed", error=str(exc))
            return EvaluationOutcome(False, "Değerlendirici çalıştırılamadı.", [])

        parsed = _parse_json_object(result.content)
        if parsed is None:
            fallback = self._rule_based_fact(user_message)
            if fallback is not None:
                return fallback
            return EvaluationOutcome(False, "Değerlendirici geçerli JSON üretmedi.", [])

        if not parsed.get("should_save"):
            return EvaluationOutcome(False, str(parsed.get("reason", ""))[:300], [])

        candidates = self._sanitize(parsed.get("candidates") or [])
        if not candidates:
            return EvaluationOutcome(False, "Adaylar filtreden geçemedi.", [])

        return EvaluationOutcome(True, str(parsed.get("reason", ""))[:300], candidates)

    def _rule_based_fact(self, user_message: str) -> EvaluationOutcome | None:
        """4B JSON üretemezse kimlik/hatırla ipuçlarını yine de kaydeder."""
        text = user_message.strip()
        if len(text) < MIN_USER_LENGTH:
            return None
        if self.contains_sensitive(text) or self.is_self_referential(text):
            return None
        if not (FACT_HINTS.search(text) or EXPLICIT_SAVE_HINTS.search(text)):
            return None
        return EvaluationOutcome(
            True,
            "Kural tabanlı kalıcı bilgi.",
            [
                MemoryCandidate(
                    content=text[:400],
                    category=MemoryCategory.FACT,
                    importance=0.7,
                    tags=["auto"],
                )
            ],
        )

    def _sanitize(self, raw_candidates: list[Any]) -> list[MemoryCandidate]:
        """LLM adaylarını doğrular, hassas olanları eler."""
        out: list[MemoryCandidate] = []
        for item in raw_candidates[:5]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if len(content) < 8 or len(content) > 1000:
                continue
            if self.contains_sensitive(content):
                logger.info("memory_candidate_rejected_sensitive")
                continue
            rejection = self.rejection_reason(content)
            if rejection is not None:
                logger.info("memory_candidate_rejected", reason=rejection)
                continue
            try:
                category = MemoryCategory(str(item.get("category", "other")).lower())
            except ValueError:
                category = MemoryCategory.OTHER
            try:
                importance = float(item.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5
            tags = [
                str(t)[:40] for t in (item.get("tags") or []) if isinstance(t, str | int | float)
            ][:10]
            out.append(
                MemoryCandidate(
                    content=content,
                    category=category,
                    importance=max(0.0, min(1.0, importance)),
                    tags=tags,
                )
            )
        return out

def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Serbest metinden ilk JSON nesnesini çıkarır."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : index + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
    return None
