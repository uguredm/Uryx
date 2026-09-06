"""Wikimedia REST özet — sabit kamu host, kabuk yok.

https://www.mediawiki.org/wiki/Wikimedia_REST_API
https://en.wikipedia.org/api/rest_v1/page/summary/{title}
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

WIKI_LANGS = {
    "tr": "tr.wikipedia.org",
    "en": "en.wikipedia.org",
    "de": "de.wikipedia.org",
}
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_MAX_EXTRACT = 2000

def normalize_wiki_lang(value: str | None) -> str:
    token = (value or "tr").strip().casefold()
    return token if token in WIKI_LANGS else "tr"

def wiki_summary_url(title: str, *, lang: str = "tr") -> str:
    """Yalnızca wikipedia.org REST özet adresi üretir."""
    clean = title.strip()
    if not clean:
        raise ToolExecutionError(
            loc("Wikipedia başlığı boş olamaz.", "Wikipedia title cannot be empty.")
        )
    host = WIKI_LANGS[normalize_wiki_lang(lang)]
    return f"https://{host}/api/rest_v1/page/summary/{quote(clean, safe='')}"

def wiki_opensearch_url(title: str, *, lang: str = "tr") -> str:
    host = WIKI_LANGS[normalize_wiki_lang(lang)]
    return (
        f"https://{host}/w/api.php?action=opensearch&search={quote(title.strip())}"
        "&limit=3&namespace=0&format=json"
    )

def _assert_wikipedia_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host.endswith(".wikipedia.org"):
        raise ToolExecutionError(
            loc(
                "Wikipedia isteği yalnızca wikipedia.org üzerinde kalır.",
                "Wikipedia requests must stay on wikipedia.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Wikipedia adresinde kullanıcı bilgisi olamaz.",
                "Wikipedia URLs cannot include user info.",
            )
        )
    return url

def _parse_summary(payload: dict[str, Any], *, requested: str, lang: str) -> dict[str, Any]:
    extract = str(payload.get("extract") or "").strip()[:_MAX_EXTRACT]
    urls = payload.get("content_urls") or {}
    desktop = urls.get("desktop") if isinstance(urls, dict) else {}
    page = str((desktop or {}).get("page") or payload.get("content_url") or "")
    return {
        "ok": True,
        "found": bool(extract or payload.get("title")),
        "title": str(payload.get("title") or requested)[:300],
        "description": str(payload.get("description") or "")[:400],
        "extract": extract,
        "url": page[:2000],
        "lang": lang,
        "kind": str(payload.get("type") or "standard"),
        "disambiguation": str(payload.get("type") or "") == "disambiguation",
    }

async def lookup_wikipedia(title: str, *, lang: str = "tr") -> dict[str, Any]:
    """Sayfa özeti; 404 ise OpenSearch ile ilk maddeye düşer."""
    clean = title.strip()
    if not clean:
        raise ToolExecutionError(
            loc("Wikipedia başlığı boş olamaz.", "Wikipedia title cannot be empty.")
        )
    locale = normalize_wiki_lang(lang)
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            summary = await _get_summary(client, clean, locale)
            if summary is not None:
                return summary
            resolved = await _opensearch_title(client, clean, locale)
            if resolved:
                summary = await _get_summary(client, resolved, locale)
                if summary is not None:
                    return {**summary, "resolved_from": clean}
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Wikipedia isteği başarısız: {exc}", f"Wikipedia request failed: {exc}")
        ) from exc
    return {
        "ok": True,
        "found": False,
        "title": clean,
        "lang": locale,
        "reason": loc(
            "Madde bulunamadı. web_search veya site=wikipedia.org dene.",
            "Article not found. Try web_search or site=wikipedia.org.",
        ),
    }

async def _get_json(client: httpx.AsyncClient, url: str) -> tuple[int, Any]:
    current = _assert_wikipedia_url(url)
    for _ in range(3):
        response = await client.get(current)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("location") or "")
            if location.startswith("/"):
                parsed = urlparse(current)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            current = _assert_wikipedia_url(location)
            continue
        if response.status_code == 404:
            return 404, None
        response.raise_for_status()
        return response.status_code, response.json()
    raise ToolExecutionError(
        loc("Wikipedia yönlendirmesi çok uzun.", "Wikipedia redirect chain is too long.")
    )

async def _get_summary(
    client: httpx.AsyncClient, title: str, lang: str
) -> dict[str, Any] | None:
    status, payload = await _get_json(client, wiki_summary_url(title, lang=lang))
    if status == 404 or not isinstance(payload, dict):
        return None
    return _parse_summary(payload, requested=title, lang=lang)

async def _opensearch_title(client: httpx.AsyncClient, title: str, lang: str) -> str:
    status, payload = await _get_json(client, wiki_opensearch_url(title, lang=lang))
    if status == 404 or not isinstance(payload, list) or len(payload) < 2:
        return ""
    titles = payload[1]
    if not isinstance(titles, list) or not titles:
        return ""
    return str(titles[0] or "").strip()
