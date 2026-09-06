"""Crossref DOI özeti — anahtarsız, sabit host, kabuk yok.

https://www.crossref.org/documentation/retrieve-metadata/rest-api/
https://api.crossref.org/works/{doi}
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

DOI_HOST = "api.crossref.org"
_USER_AGENT = (
    "Uryx/1.0.0 (local-assistant; mailto:uryx@localhost; "
    "+https://github.com/uguredm/Uryx)"
)
_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$", re.IGNORECASE)

def normalize_doi(value: str) -> str:
    token = (value or "").strip()
    token = re.sub(r"^https?://(dx\.)?doi\.org/", "", token, flags=re.IGNORECASE)
    token = token.removeprefix("doi:").strip()
    if not _DOI_RE.match(token) or len(token) > 200:
        raise ToolExecutionError(
            loc("DOI 10.xxxx/... biçiminde olmalı.", "DOI must be in 10.xxxx/... form.")
        )
    return token

def doi_url(doi: str) -> str:
    clean = normalize_doi(doi)
    return f"https://{DOI_HOST}/works/{quote(clean, safe='/')}"

def _assert_crossref(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != DOI_HOST:
        raise ToolExecutionError(
            loc(
                "DOI isteği yalnızca api.crossref.org üzerinde kalır.",
                "DOI requests must stay on api.crossref.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("DOI adresinde kullanıcı bilgisi olamaz.", "DOI URLs cannot include user info.")
        )
    return url

def _authors(message: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for item in (message.get("author") or [])[:8]:
        if not isinstance(item, dict):
            continue
        family = str(item.get("family") or "").strip()
        given = str(item.get("given") or "").strip()
        name = " ".join(part for part in (given, family) if part)[:120]
        if name:
            rows.append(name)
    return rows

async def lookup_doi(doi: str) -> dict[str, Any]:
    """Tek bir DOI kaydının başlık/yazar/yıl özetini okur."""
    url = _assert_crossref(doi_url(doi))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "DOI API yönlendirmesi kabul edilmez.",
                        "DOI API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "doi": normalize_doi(doi),
                    "reason": loc(
                        "DOI bulunamadı. wiki_lookup veya web_search dene.",
                        "DOI not found. Try wiki_lookup or web_search.",
                    ),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"DOI kaydı alınamadı: {exc}", f"Could not fetch DOI record: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("DOI yanıtı geçersiz.", "DOI response is invalid."))
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    titles = message.get("title") if isinstance(message.get("title"), list) else []
    published = message.get("published-print") or message.get("published-online") or {}
    year_parts = published.get("date-parts") if isinstance(published, dict) else None
    year_parts = year_parts or [[]]
    year = year_parts[0][0] if year_parts and year_parts[0] else None
    return {
        "ok": True,
        "found": True,
        "doi": str(message.get("DOI") or normalize_doi(doi))[:200],
        "title": str(titles[0] if titles else "")[:400],
        "authors": _authors(message),
        "year": year,
        "type": str(message.get("type") or "")[:80],
        "publisher": str(message.get("publisher") or "")[:160],
        "container": str((message.get("container-title") or [""])[0] or "")[:200],
        "url": str(message.get("URL") or "")[:2000],
        "source": DOI_HOST,
    }
