"""Wiktionary REST sözlük — sabit kamu host, kabuk yok.

https://en.wiktionary.org/api/rest_v1/page/definition/{term}
https://www.mediawiki.org/wiki/Wikimedia_REST_API
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

DICT_LANGS = {
    "tr": "tr.wiktionary.org",
    "en": "en.wiktionary.org",
    "de": "de.wiktionary.org",
}
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_MAX_DEF = 400
_HTML_TAG = re.compile(r"<[^>]+>")

def normalize_dict_lang(value: str | None) -> str:
    token = (value or "tr").strip().casefold()
    return token if token in DICT_LANGS else "tr"

def dict_definition_url(term: str, *, lang: str = "tr") -> str:
    clean = term.strip()
    if not clean:
        raise ToolExecutionError(
            loc("Sözlük terimi boş olamaz.", "Dictionary term cannot be empty.")
        )
    host = DICT_LANGS[normalize_dict_lang(lang)]
    return f"https://{host}/api/rest_v1/page/definition/{quote(clean, safe='')}"

def dict_summary_url(term: str, *, lang: str = "tr") -> str:
    clean = term.strip()
    if not clean:
        raise ToolExecutionError(
            loc("Sözlük terimi boş olamaz.", "Dictionary term cannot be empty.")
        )
    host = DICT_LANGS[normalize_dict_lang(lang)]
    return f"https://{host}/api/rest_v1/page/summary/{quote(clean, safe='')}"

def dict_opensearch_url(term: str, *, lang: str = "tr") -> str:
    host = DICT_LANGS[normalize_dict_lang(lang)]
    return (
        f"https://{host}/w/api.php?action=opensearch&search={quote(term.strip())}"
        "&limit=3&namespace=0&format=json"
    )

def _assert_wiktionary_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host.endswith(".wiktionary.org"):
        raise ToolExecutionError(
            loc(
                "Sözlük isteği yalnızca wiktionary.org üzerinde kalır.",
                "Dictionary requests must stay on wiktionary.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Sözlük adresinde kullanıcı bilgisi olamaz.",
                "Dictionary URLs cannot include user info.",
            )
        )
    return url

def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text).strip()

def _parse_definitions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for lang_key, groups in payload.items():
        if not isinstance(groups, list):
            continue
        for group in groups[:4]:
            if not isinstance(group, dict):
                continue
            defs: list[str] = []
            for item in (group.get("definitions") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                text = _strip_html(str(item.get("definition") or ""))[:_MAX_DEF]
                if text:
                    defs.append(text)
            if not defs:
                continue
            entries.append(
                {
                    "language": str(group.get("language") or lang_key)[:80],
                    "part_of_speech": str(group.get("partOfSpeech") or "")[:80],
                    "definitions": defs,
                }
            )
            if len(entries) >= 8:
                return entries
    return entries

def _parse_summary(payload: dict[str, Any], *, requested: str, lang: str) -> dict[str, Any]:
    extract = _strip_html(str(payload.get("extract") or ""))[:2000]
    urls = payload.get("content_urls") or {}
    desktop = urls.get("desktop") if isinstance(urls, dict) else {}
    page = str((desktop or {}).get("page") or "")
    return {
        "ok": True,
        "found": bool(extract or payload.get("title")),
        "term": str(payload.get("title") or requested)[:300],
        "extract": extract,
        "url": page[:2000],
        "lang": lang,
        "kind": "summary",
        "entries": [],
    }

async def lookup_dictionary(term: str, *, lang: str = "tr") -> dict[str, Any]:
    """Yapılandırılmış tanım; yoksa özet; 404'te OpenSearch."""
    clean = term.strip()
    if not clean:
        raise ToolExecutionError(
            loc("Sözlük terimi boş olamaz.", "Dictionary term cannot be empty.")
        )
    locale = normalize_dict_lang(lang)
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            defined = await _get_definition(client, clean, locale)
            if defined is not None:
                return defined
            summary = await _get_summary(client, clean, locale)
            if summary is not None:
                return summary
            resolved = await _opensearch_title(client, clean, locale)
            if resolved:
                defined = await _get_definition(client, resolved, locale)
                if defined is not None:
                    return {**defined, "resolved_from": clean}
                summary = await _get_summary(client, resolved, locale)
                if summary is not None:
                    return {**summary, "resolved_from": clean}
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Sözlük isteği başarısız: {exc}", f"Dictionary request failed: {exc}")
        ) from exc
    return {
        "ok": True,
        "found": False,
        "term": clean,
        "lang": locale,
        "reason": loc(
            "Madde bulunamadı. wiki_lookup veya web_search dene.",
            "Article not found. Try wiki_lookup or web_search.",
        ),
    }

async def _get_json(client: httpx.AsyncClient, url: str) -> tuple[int, Any]:
    current = _assert_wiktionary_url(url)
    for _ in range(3):
        response = await client.get(current)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("location") or "")
            if location.startswith("/"):
                parsed = urlparse(current)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            current = _assert_wiktionary_url(location)
            continue
        if response.status_code == 404:
            return 404, None
        response.raise_for_status()
        return response.status_code, response.json()
    raise ToolExecutionError(
        loc("Sözlük yönlendirmesi çok uzun.", "Dictionary redirect chain is too long.")
    )

async def _get_definition(
    client: httpx.AsyncClient, term: str, lang: str
) -> dict[str, Any] | None:
    status, payload = await _get_json(client, dict_definition_url(term, lang=lang))
    if status == 404 or not isinstance(payload, dict):
        return None
    entries = _parse_definitions(payload)
    if not entries:
        return None
    return {
        "ok": True,
        "found": True,
        "term": term[:300],
        "lang": lang,
        "kind": "definition",
        "entries": entries,
        "extract": entries[0]["definitions"][0] if entries[0]["definitions"] else "",
    }

async def _get_summary(
    client: httpx.AsyncClient, term: str, lang: str
) -> dict[str, Any] | None:
    status, payload = await _get_json(client, dict_summary_url(term, lang=lang))
    if status == 404 or not isinstance(payload, dict):
        return None
    return _parse_summary(payload, requested=term, lang=lang)

async def _opensearch_title(client: httpx.AsyncClient, term: str, lang: str) -> str:
    status, payload = await _get_json(client, dict_opensearch_url(term, lang=lang))
    if status == 404 or not isinstance(payload, list) or len(payload) < 2:
        return ""
    titles = payload[1]
    if not isinstance(titles, list) or not titles:
        return ""
    return str(titles[0] or "").strip()
