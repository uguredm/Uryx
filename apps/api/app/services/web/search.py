"""Anahtarsız, birden fazla arama sağlayıcısını kullanan web araması."""

from __future__ import annotations

import asyncio
import calendar
import ipaddress
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

NEWS_REGIONS = ("tr-tr", "wt-wt", "us-en", "uk-en", "de-de")
NEWS_SAFES = ("on", "moderate", "off")
NEWS_WINDOWS = ("d", "w", "m")

SEARCH_WINDOWS = ("d", "w", "m", "y")
SEARCH_FILETYPES = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "html")
_SITE_HOST_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)

def normalize_news_region(value: str | None, *, default: str = "wt-wt") -> str:
    """Allowlist bölge kodu; bilinmeyen değer varsayılana düşer."""
    token = (value or "").strip().casefold()
    if token in NEWS_REGIONS:
        return token
    return default if default in NEWS_REGIONS else "wt-wt"

def normalize_news_safesearch(value: str | None, *, default: str = "moderate") -> str:
    token = (value or "").strip().casefold()
    if token in NEWS_SAFES:
        return token
    return default if default in NEWS_SAFES else "moderate"

def normalize_news_timelimit(value: str | None, *, default: str = "w") -> str:
    token = (value or "").strip().casefold()
    if token in NEWS_WINDOWS:
        return token
    return default if default in NEWS_WINDOWS else "w"

def news_item_matches_source(item: dict[str, str], source: str) -> bool:
    """Kaynak adı veya hostname (www. yok) ile daraltır."""
    needle = source.strip().casefold().removeprefix("www.")
    if not needle:
        return True
    host = (urlparse(str(item.get("url") or "")).hostname or "").casefold().removeprefix(
        "www."
    )
    label = str(item.get("source") or "").casefold()
    return needle in host or needle in label

def filter_news_by_source(results: list[dict[str, str]], source: str) -> list[dict[str, str]]:
    """Haber listesini kaynak/alan adına göre süzgeçler."""
    if not source.strip():
        return results
    return [item for item in results if news_item_matches_source(item, source)]

def normalize_search_timelimit(value: str | None) -> str | None:
    """Boş = filtresiz; aksi halde d/w/m/y."""
    token = (value or "").strip().casefold()
    if not token:
        return None
    return token if token in SEARCH_WINDOWS else None

def normalize_search_filetype(value: str | None) -> str:
    token = (value or "").strip().casefold().lstrip(".")
    if not token:
        return ""
    if token not in SEARCH_FILETYPES:
        raise ToolExecutionError(
            loc(
                "filetype yalnızca pdf, doc, docx, xls, xlsx, ppt, pptx veya html olabilir.",
                "filetype must be pdf, doc, docx, xls, xlsx, ppt, pptx, or html.",
            )
        )
    return token

def normalize_search_site(value: str | None) -> str:
    """Yalnızca genel alan adı; şema/yol/IP yok (site: enjeksiyonu yok)."""
    token = (value or "").strip().casefold()
    if not token:
        return ""
    token = token.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    token = token.split("/", 1)[0].split("?", 1)[0]
    if token in {"localhost"} or token.endswith((".local", ".localhost", ".internal")):
        raise ToolExecutionError(
            loc("site yerel veya özel bir alan olamaz.", "site cannot be a local or private domain.")
        )
    try:
        address = ipaddress.ip_address(token)
    except ValueError:
        address = None
    if address is not None:
        raise ToolExecutionError(
            loc(
                "site IP adresi olamaz; genel alan adı kullan.",
                "site cannot be an IP address; use a public domain name.",
            )
        )
    if not _SITE_HOST_RE.fullmatch(token):
        raise ToolExecutionError(
            loc(
                "site yalnızca genel alan adı olabilir (ör. wikipedia.org).",
                "site must be a public domain name (e.g. wikipedia.org).",
            )
        )
    return token

def compose_search_query(
    query: str, *, site: str = "", filetype: str = "", exclude_site: str = ""
) -> str:
    """DDG site:/filetype:/-site: sözdizimini güvenli parametrelerden üretir."""
    parts = [query.strip()]
    host = normalize_search_site(site)
    blocked = normalize_search_site(exclude_site)
    kind = normalize_search_filetype(filetype)
    if host and blocked and host == blocked:
        raise ToolExecutionError(
            loc("site ve exclude_site aynı olamaz.", "site and exclude_site cannot be the same.")
        )
    if host:
        parts.append(f"site:{host}")
    if blocked:
        parts.append(f"-site:{blocked}")
    if kind:
        parts.append(f"filetype:{kind}")
    return " ".join(part for part in parts if part)

def result_excluded_by_site(item: dict[str, str], exclude_site: str) -> bool:
    """DDG -site: kaçırırsa hostname ile düşür."""
    blocked = normalize_search_site(exclude_site)
    if not blocked:
        return False
    host = (urlparse(str(item.get("url") or "")).hostname or "").casefold().removeprefix(
        "www."
    )
    return host == blocked or host.endswith(f".{blocked}")

class WebSearchService:
    """DDGS üzerinden canlı web araması yapar."""

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        region: str = "tr-tr",
        timelimit: str | None = None,
        site: str = "",
        filetype: str = "",
        exclude_site: str = "",
    ) -> list[dict[str, str]]:
        clean_query = compose_search_query(
            query, site=site, filetype=filetype, exclude_site=exclude_site
        )
        if not clean_query:
            raise ToolExecutionError(
                loc("Arama sorgusu boş olamaz.", "Search query cannot be empty.")
            )
        limit = max(1, min(max_results, 8))
        locale = normalize_news_region(region, default="tr-tr")
        window = normalize_search_timelimit(timelimit)

        def _search() -> list[dict[str, str]]:
            try:
                from ddgs import DDGS

                raw: list[dict[str, Any]] = DDGS(timeout=12).text(
                    clean_query,
                    region=locale,
                    safesearch="moderate",
                    timelimit=window,
                    max_results=limit,
                )
            except Exception as exc:
                raise ToolExecutionError(
                    loc(f"İnternet araması başarısız: {exc}", f"Web search failed: {exc}")
                ) from exc

            results: list[dict[str, str]] = []
            for item in raw or []:
                url = str(item.get("href") or item.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                results.append(
                    {
                        "title": str(item.get("title") or url).strip()[:300],
                        "summary": str(item.get("body") or item.get("description") or "").strip()[
                            :1200
                        ],
                        "url": url[:2000],
                    }
                )
            if exclude_site.strip():
                results = [
                    item for item in results if not result_excluded_by_site(item, exclude_site)
                ]
            return results

        return await asyncio.to_thread(_search)

    async def research(self, query: str, *, max_results: int = 10) -> list[dict[str, str]]:
        """Run diverse searches in parallel and return a deduplicated evidence set."""
        clean_query = query.strip()
        if not clean_query:
            raise ToolExecutionError(
                loc("Araştırma sorgusu boş olamaz.", "Research query cannot be empty.")
            )
        limit = max(3, min(max_results, 12))
        year = datetime.now(UTC).year
        variants = [
            clean_query,
            f"{clean_query} {year}",
            f"{clean_query} resmi kaynak official",
        ]
        if re.search(r"\b(son|en son|latest|newest|güncel|guncel)\b", clean_query.casefold()):
            variants.append(f'"{clean_query}" yayın tarihi release date {year}')
        batches = await asyncio.gather(
            *(self.search(variant, max_results=5) for variant in variants),
            return_exceptions=True,
        )
        merged: list[dict[str, str]] = []
        seen: set[str] = set()
        valid_batches = [batch for batch in batches if not isinstance(batch, BaseException)]
        max_batch_size = max((len(batch) for batch in valid_batches), default=0)
        for index in range(max_batch_size):
            for batch in valid_batches:
                if index >= len(batch):
                    continue
                item = batch[index]
                normalized = item["url"].split("#", 1)[0].rstrip("/")
                if normalized in seen:
                    continue
                seen.add(normalized)
                domain = urlparse(item["url"]).hostname or ""
                merged.append({**item, "domain": domain.removeprefix("www.")})
                if len(merged) >= limit:
                    return merged
        return merged

    async def news(
        self,
        query: str,
        *,
        max_results: int = 10,
        timelimit: str = "m",
        region: str = "wt-wt",
        safesearch: str = "moderate",
        source: str = "",
    ) -> list[dict[str, str]]:
        """Search recent news so time-sensitive social lookups do not rely on stale snippets."""
        clean_query = query.strip()
        if not clean_query:
            raise ToolExecutionError(
                loc("Haber arama sorgusu boş olamaz.", "News search query cannot be empty.")
            )
        limit = max(1, min(max_results, 12))
        window = normalize_news_timelimit(timelimit, default="m")
        locale = normalize_news_region(region, default="wt-wt")
        safe = normalize_news_safesearch(safesearch)
        fetch_limit = min(12, limit * 2) if source.strip() else limit

        def _search() -> list[dict[str, str]]:
            try:
                from ddgs import DDGS

                raw: list[dict[str, Any]] = DDGS(timeout=12).news(
                    clean_query,
                    region=locale,
                    safesearch=safe,
                    timelimit=window,
                    max_results=fetch_limit,
                )
            except Exception as exc:
                raise ToolExecutionError(
                    loc(f"Güncel haber araması başarısız: {exc}", f"News search failed: {exc}")
                ) from exc

            results: list[dict[str, str]] = []
            for item in raw or []:
                url = str(item.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                results.append(
                    {
                        "title": str(item.get("title") or url).strip()[:300],
                        "summary": str(item.get("body") or "").strip()[:1200],
                        "url": url[:2000],
                        "published": str(item.get("date") or "")[:40],
                        "source": str(item.get("source") or "")[:200],
                    }
                )
            return filter_news_by_source(results, source)[:limit]

        return await asyncio.to_thread(_search)

    async def image_search(self, query: str, *, max_results: int = 6) -> list[dict[str, str | int]]:
        """Görsel arama sonucu ve kaynak adreslerini döndürür."""
        clean_query = query.strip()
        if not clean_query:
            raise ToolExecutionError(
                loc("Görsel arama sorgusu boş olamaz.", "Image search query cannot be empty.")
            )
        limit = max(1, min(max_results, 12))
        instagram_only = "instagram" in clean_query.casefold()

        def _search() -> list[dict[str, str | int]]:
            try:
                from ddgs import DDGS

                raw: list[dict[str, Any]] = DDGS(timeout=12).images(
                    clean_query,
                    region="tr-tr",
                    safesearch="moderate",
                    max_results=limit,
                )
            except Exception as exc:
                raise ToolExecutionError(
                    loc(f"Görsel araması başarısız: {exc}", f"Image search failed: {exc}")
                ) from exc

            images: list[dict[str, str | int]] = []
            fallback_images: list[dict[str, str | int]] = []
            for item in raw or []:
                image_url = str(item.get("image") or "").strip()
                thumbnail = str(item.get("thumbnail") or image_url).strip()
                source_url = str(item.get("url") or "").strip()
                if not image_url.startswith(("http://", "https://")):
                    continue
                row: dict[str, str | int] = {
                    "title": str(item.get("title") or clean_query).strip()[:300],
                    "image": image_url[:3000],
                    "thumbnail": thumbnail[:3000],
                    "source": source_url[:3000],
                    "width": int(item.get("width") or 0),
                    "height": int(item.get("height") or 0),
                    "platform_verified": int("instagram.com/" in source_url.casefold()),
                }
                fallback_images.append(row)
                if not instagram_only or int(row["platform_verified"]) == 1:
                    images.append(row)
            return images or fallback_images

        return await asyncio.to_thread(_search)

    async def social_profile(self, query: str) -> dict[str, Any]:
        """Resolve an official Instagram profile and its newest indexed post."""
        subject = _social_search_subject(query)
        if not subject:
            raise ToolExecutionError(
                loc(
                    "Sosyal medya hesabı için kişi veya marka adı gerekli.",
                    "A person or brand name is required for a social media account lookup.",
                )
            )
        now = datetime.now(UTC)
        year = now.year
        evidence = await self.research(
            f"{subject} official Instagram profile latest post {year}", max_results=12
        )
        global_queries = [
            f"{subject} latest Instagram post {calendar.month_name[now.month]} {year}",
            f"{subject} newest Instagram post {year}",
            f'site:instagram.com "{subject}" Instagram post {year}',
        ]
        global_batches = await asyncio.gather(
            *(self.search(item, max_results=10, region="wt-wt") for item in global_queries),
            self.news(f"{subject} Instagram", max_results=12, timelimit="m"),
            self.news(f"{subject} Instagram photos", max_results=12, timelimit="m"),
            return_exceptions=True,
        )
        seen = {item["url"].split("#", 1)[0].rstrip("/") for item in evidence}
        for batch in global_batches:
            if isinstance(batch, BaseException):
                continue
            for item in batch:
                normalized = item["url"].split("#", 1)[0].rstrip("/")
                if normalized in seen:
                    continue
                seen.add(normalized)
                domain = urlparse(item["url"]).hostname or ""
                evidence.append({**item, "domain": domain.removeprefix("www.")})
        resolved = _resolve_instagram_profile(subject, evidence)
        caption = str(resolved.get("latest_post_caption") or "").strip()
        if resolved.get("resolved") and caption:
            quoted = " ".join(caption.split())[:180].replace('"', "")
            try:
                coverage = await self.search(f'{subject} "{quoted}"', max_results=8, region="wt-wt")
            except ToolExecutionError:
                coverage = []
            for item in coverage:
                normalized = item["url"].split("#", 1)[0].rstrip("/")
                if normalized in seen:
                    continue
                seen.add(normalized)
                domain = urlparse(item["url"]).hostname or ""
                evidence.append({**item, "domain": domain.removeprefix("www.")})

        if resolved.get("resolved"):
            ranked_coverage = _rank_social_coverage(
                evidence,
                subject=subject,
                caption=caption,
                indexed_date=str(resolved.get("latest_post_date") or ""),
            )
            candidates = ranked_coverage[:6]
            embedded_posts = await asyncio.gather(
                *(_embedded_instagram_post(item["url"]) for item in candidates[:4]),
                return_exceptions=True,
            )
            preferred_index = 0
            verified_embedded = False
            current_url = str(resolved.get("latest_post_url") or "")
            current_date = _date_tuple(str(resolved.get("latest_post_date") or ""))
            newest_coverage_date = _coverage_date(candidates[0]) if candidates else (0, 0, 0)
            for index, embedded in enumerate(embedded_posts):
                if isinstance(embedded, BaseException) or not embedded:
                    continue
                candidate_date = _coverage_date(candidates[index])
                if not _dates_within_days(candidate_date, newest_coverage_date, 14):
                    continue
                preferred_index = index
                verified_embedded = True
                if not current_url or candidate_date >= current_date:
                    resolved["latest_post_url"] = embedded
                    if embedded != current_url and candidate_date != (0, 0, 0):
                        resolved["latest_post_date"] = "-".join(map(str, candidate_date))
                break
            if candidates:
                if not verified_embedded and newest_coverage_date > current_date:
                    resolved["latest_post_url"] = ""
                    resolved["latest_post_date"] = "-".join(map(str, newest_coverage_date))
                    resolved["latest_post_title"] = candidates[0]["title"]
                    resolved["latest_post_caption"] = ""
                candidates.insert(0, candidates.pop(preferred_index))
                resolved["coverage_url"] = candidates[0]["url"]
                resolved["coverage_title"] = candidates[0]["title"]
                resolved["coverage_candidates"] = [
                    {
                        "url": item["url"],
                        "title": item["title"],
                        "published": item.get("published", ""),
                    }
                    for item in candidates
                ]
        return resolved

    async def video_search(self, query: str, *, max_results: int = 6) -> list[dict[str, str]]:
        """Video sayfalarını arar ve oynatılabilir sonuçları küçük resimleriyle döndürür."""
        clean_query = query.strip()
        if not clean_query:
            raise ToolExecutionError(
                loc("Video arama sorgusu boş olamaz.", "Video search query cannot be empty.")
            )
        limit = max(1, min(max_results, 10))
        subject = _video_search_subject(clean_query)
        videos = await asyncio.to_thread(_search_youtube_with_ytdlp, subject, limit)
        if videos:
            return videos

        search_query = f"{subject} video YouTube"
        results = await self.search(search_query, max_results=min(8, limit + 2))

        videos = []
        seen: set[str] = set()
        for item in results:
            url = item["url"]
            video_id = _youtube_video_id(url)
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            videos.append(
                {
                    "title": item["title"],
                    "summary": item["summary"],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    "provider": "YouTube",
                }
            )
            if len(videos) >= limit:
                break
        return videos

def _youtube_video_id(url: str) -> str | None:
    """Extract a conservative YouTube video id from a public result URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.hostname.casefold() if parsed.hostname else ""
    candidate = ""
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/shorts/"):
            candidate = parsed.path.split("/")[2]
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None

def _video_search_subject(query: str) -> str:
    """Remove conversational request words that reduce search-engine precision."""
    subject = query.casefold()
    subject = re.sub(r"\byoutube(?:'dan|dan|den)?\b", " ", subject)
    subject = re.sub(r"\b(video(?:su|sunu|ları|lari)?|klip(?:i|leri)?)\b", " ", subject)
    subject = re.sub(
        r"\b(getir(?:ir)?|göster(?:ir)?|goster(?:ir)?|bul|ara)(?:\s+misin|\s+mısın)?\b",
        " ",
        subject,
    )
    subject = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]+", " ", subject, flags=re.UNICODE)
    return " ".join(subject.split()) or query.strip()

def _social_search_subject(query: str) -> str:
    """Extract the named person or brand from an Instagram retrieval request."""
    before_instagram = re.split(r"\binstagram\b", query, maxsplit=1, flags=re.IGNORECASE)[0]
    subject = re.sub(r"['’](?:ın|in|un|ün)\b", "", before_instagram, flags=re.IGNORECASE)
    subject = re.sub(
        r"\b(?:bana|lütfen|lutfen|profil|hesap|resmi|official|son|en son|güncel|guncel|"
        r"gönderi|gonderi|paylaşım|paylasim|post|fotoğraf|fotograf|foto|görsel|gorsel|"
        r"bul|getir|göster|goster|ara|bak|uryx|hey|mısın|misin)\w*\b",
        " ",
        subject,
        flags=re.IGNORECASE,
    )
    subject = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]+", " ", subject, flags=re.UNICODE)
    return " ".join(subject.split())

def _resolve_instagram_profile(subject: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
    """Rank Instagram handles and reject unrelated profiles deterministically."""
    reserved = {
        "about",
        "accounts",
        "developer",
        "directory",
        "explore",
        "p",
        "popular",
        "reel",
        "reels",
        "stories",
    }
    subject_key = _identity_key(subject)
    subject_words = set(_identity_words(subject))
    candidates: dict[str, dict[str, Any]] = {}

    for item in evidence:
        url = str(item.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        if host != "instagram.com":
            continue
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if not parts or parts[0].casefold() in reserved:
            continue
        handle = parts[0].lstrip("@").casefold()
        if not re.fullmatch(r"[a-z0-9._]{1,30}", handle):
            continue

        text = " ".join([str(item.get("title") or ""), str(item.get("summary") or ""), handle])
        words = set(_identity_words(text))
        entry = candidates.setdefault(
            handle,
            {"score": 0, "mentions": 0, "profile_urls": [], "evidence": []},
        )
        entry["mentions"] += 1
        entry["score"] += 4
        if _identity_key(handle) == subject_key:
            entry["score"] += 70
        if subject_words and subject_words <= words:
            entry["score"] += 20
        if "official" in text.casefold() or f"(@{handle})" in text.casefold():
            entry["score"] += 10
        if len(parts) == 1:
            entry["score"] += 8
            entry["profile_urls"].append(url)
        entry["evidence"].append(item)

    if not candidates:
        return {
            "resolved": False,
            "subject": subject,
            "reason": loc(
                "Doğrulanabilir bir Instagram profili bulunamadı.",
                "No verifiable Instagram profile was found.",
            ),
            "evidence": evidence[:8],
        }

    handle, winner = max(
        candidates.items(),
        key=lambda pair: (int(pair[1]["score"]), int(pair[1]["mentions"])),
    )
    if int(winner["score"]) < 45:
        return {
            "resolved": False,
            "subject": subject,
            "reason": loc(
                "Bulunan Instagram profili kişi adıyla yeterince eşleşmiyor.",
                "The Instagram profile found does not match the person's name closely enough.",
            ),
            "evidence": evidence[:8],
        }

    content_candidates: list[tuple[tuple[int, int, int], str, dict[str, str]]] = []
    for item in evidence:
        url = str(item.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        if host != "instagram.com":
            continue
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            continue
        text = " ".join([str(item.get("title") or ""), str(item.get("summary") or "")])
        owner_match = re.search(
            r"(?:^|[-·])\s*@?([a-z0-9._]{1,30})\s+on\s+(?:[A-Za-z]+\s+\d|\d)",
            text,
            re.IGNORECASE,
        )
        owner_confirmed = bool(owner_match and owner_match.group(1).casefold() == handle)
        is_content = parts[0].casefold() in {"p", "reel", "reels"}
        is_scoped_content = (
            parts[0].casefold() == handle
            and len(parts) >= 3
            and parts[1].casefold() in {"p", "reel", "reels"}
        )
        if not is_scoped_content and not (is_content and owner_confirmed):
            continue
        content_candidates.append((_indexed_date(text), url, item))

    content_candidates.sort(key=lambda row: row[0], reverse=True)
    latest_url = content_candidates[0][1] if content_candidates else ""
    latest_item = content_candidates[0][2] if content_candidates else {}
    latest_date = ""
    if content_candidates and content_candidates[0][0] != (0, 0, 0):
        latest_date = "-".join(str(part) for part in content_candidates[0][0])

    return {
        "resolved": True,
        "subject": subject,
        "handle": handle,
        "profile_url": f"https://www.instagram.com/{handle}/",
        "latest_post_url": latest_url,
        "latest_post_date": latest_date,
        "latest_post_title": str(latest_item.get("title") or ""),
        "latest_post_caption": _extract_post_caption(str(latest_item.get("summary") or "")),
        "confidence": min(100, int(winner["score"])),
        "evidence_count": len(evidence),
        "evidence": evidence[:8],
    }

def _identity_key(value: str) -> str:
    return "".join(_identity_words(value))

def _identity_words(value: str) -> list[str]:
    normalized = (
        value.casefold()
        .replace("ç", "c")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
    )
    return re.findall(r"[a-z0-9]+", normalized)

def _indexed_date(value: str) -> tuple[int, int, int]:
    """Parse common English/Turkish search-result dates for stable newest-first sorting."""
    months = {
        "jan": 1,
        "ocak": 1,
        "feb": 2,
        "şub": 2,
        "sub": 2,
        "mar": 3,
        "apr": 4,
        "nis": 4,
        "may": 5,
        "mayıs": 5,
        "mayis": 5,
        "jun": 6,
        "haz": 6,
        "jul": 7,
        "tem": 7,
        "aug": 8,
        "ağu": 8,
        "agu": 8,
        "sep": 9,
        "eyl": 9,
        "oct": 10,
        "eki": 10,
        "nov": 11,
        "kas": 11,
        "dec": 12,
        "ara": 12,
    }
    match = re.search(
        r"\b([A-Za-zÇĞİÖŞÜçğıöşü]{3,8})\s+(\d{1,2}),?\s+(20\d{2})\b",
        value,
    )
    if match:
        month = months.get(match.group(1).casefold()[:3], 0)
        return int(match.group(3)), month, int(match.group(2))
    match = re.search(
        r"\b(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]{3,8})\s+(20\d{2})\b",
        value,
    )
    if match:
        month = months.get(match.group(2).casefold()[:3], 0)
        return int(match.group(3)), month, int(match.group(1))
    return 0, 0, 0

def _extract_post_caption(summary: str) -> str:
    """Extract an indexed Instagram caption without returning engagement/date boilerplate."""
    quoted = re.search(r":\s*[\"“]([^\"”]{3,500})[\"”]", summary)
    return " ".join(quoted.group(1).split()) if quoted else ""

def _select_social_coverage(
    results: list[dict[str, str]],
    *,
    subject: str,
    caption: str,
    indexed_date: str,
) -> dict[str, str] | None:
    """Return the strongest current article covering the requested social post."""
    ranked = _rank_social_coverage(
        results,
        subject=subject,
        caption=caption,
        indexed_date=indexed_date,
    )
    return ranked[0] if ranked else None

def _rank_social_coverage(
    results: list[dict[str, str]],
    *,
    subject: str,
    caption: str,
    indexed_date: str,
) -> list[dict[str, str]]:
    """Rank recent, subject-matching Instagram coverage newest first."""
    subject_words = set(_identity_words(subject))
    caption_words = {word for word in _identity_words(caption) if len(word) >= 5}
    date_parts = [int(part) for part in indexed_date.split("-") if part.isdigit()]
    date_fragments: set[str] = set()
    reference_date: tuple[int, int, int] = (
        (date_parts[0], date_parts[1], date_parts[2]) if len(date_parts) == 3 else (0, 0, 0)
    )
    if len(date_parts) == 3:
        year, month, day = date_parts
        date_fragments = {
            f"/{year}/{month:02d}/{day:02d}/",
            f"/{year}/{month}/{day}/",
            f"{year}-{month:02d}-{day:02d}",
        }

    ranked: list[tuple[tuple[int, int, int], int, dict[str, str]]] = []
    for item in results:
        if "instagram.com" in item["url"].casefold():
            continue
        text = item["title"] + " " + item["summary"]
        lowered = text.casefold()
        text_words = set(_identity_words(text))
        if not subject_words or not subject_words <= text_words:
            continue
        if "instagram" not in lowered:
            continue
        if not re.search(
            r"\b(photo|photos|picture|pictures|post|posts|snap|snaps|carousel|"
            r"foto|fotograf|gonderi|paylas)\w*\b",
            " ".join(_identity_words(text)),
        ):
            continue
        score = 30
        caption_overlap = len(caption_words & text_words)
        score += min(30, caption_overlap * 3)
        if any(fragment in item["url"] for fragment in date_fragments):
            score += 60
        if "latest" in lowered or "new " in lowered or "yeni" in lowered:
            score += 10
        coverage_date = _coverage_date(item)
        if caption_overlap >= 3 and reference_date > coverage_date:
            coverage_date = reference_date
        ranked.append((coverage_date, score, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in ranked]

def _coverage_date(item: dict[str, str]) -> tuple[int, int, int]:
    """Read an article date from provider metadata, URL, or result text."""
    published = str(item.get("published") or "")
    match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})(?=T|\s|$)", published)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    match = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)", item["url"])
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return _indexed_date(item["title"] + " " + item["summary"])

def _date_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(part) for part in value.split("-") if part.isdigit()]
    if len(parts) != 3:
        return (0, 0, 0)
    return parts[0], parts[1], parts[2]

def _dates_within_days(
    candidate: tuple[int, int, int], newest: tuple[int, int, int], limit: int
) -> bool:
    if candidate == (0, 0, 0) or newest == (0, 0, 0):
        return False
    try:
        delta = datetime(*newest).date() - datetime(*candidate).date()
    except ValueError:
        return False
    return 0 <= delta.days <= limit

async def _embedded_instagram_post(url: str) -> str:
    """Extract the post permalink embedded by a public coverage page."""
    if not _is_public_http_url(url):
        return ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(
            timeout=12.0, headers=headers, follow_redirects=False
        ) as client:
            response = await client.get(url)
            if response.is_redirect:
                redirect = str(response.headers.get("location") or "")
                if redirect.startswith("/"):
                    parsed = urlparse(url)
                    redirect = f"{parsed.scheme}://{parsed.netloc}{redirect}"
                if not _is_public_http_url(redirect):
                    return ""
                response = await client.get(redirect)
            response.raise_for_status()
            if int(response.headers.get("content-length") or 0) > 5_000_000:
                return ""
            return _instagram_post_urls_from_html(response.text[:5_000_000])[0]
    except (httpx.HTTPError, ValueError, IndexError):
        return ""

def _instagram_post_urls_from_html(value: str) -> list[str]:
    """Canonicalize direct Instagram post URLs from ordinary or JSON-escaped HTML."""
    decoded = value.replace("\\/", "/").replace("\\u002F", "/")
    matches = re.findall(
        r"https?://(?:www\.)?instagram\.com/(p|reel|reels)/([A-Za-z0-9_-]{5,64})",
        decoded,
        flags=re.IGNORECASE,
    )
    urls: list[str] = []
    for kind, shortcode in matches:
        canonical = f"https://www.instagram.com/{kind.casefold()}/{shortcode}/"
        if canonical not in urls:
            urls.append(canonical)
    return urls

def _is_public_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host or host in {"localhost"}:
            return False
        if host.endswith((".local", ".localhost", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return "." in host
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
        )
    except ValueError:
        return False

def _search_youtube_with_ytdlp(subject: str, limit: int) -> list[dict[str, str]]:
    """Use yt-dlp's maintained YouTube extractor without downloading media."""
    try:
        from yt_dlp import YoutubeDL

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": limit,
        }
        with YoutubeDL(options) as client:
            payload = client.extract_info(f"ytsearch{limit}:{subject}", download=False)
    except Exception:
        return []

    videos: list[dict[str, str]] = []
    for entry in (payload or {}).get("entries") or []:
        video_id = str(entry.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue
        videos.append(
            {
                "title": str(entry.get("title") or subject)[:300],
                "summary": str(entry.get("description") or "")[:1200],
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": str(entry.get("thumbnail") or "")
                or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                "provider": "YouTube",
                "channel": str(entry.get("channel") or entry.get("uploader") or "")[:200],
                "duration": str(entry.get("duration") or ""),
            }
        )
    return videos
