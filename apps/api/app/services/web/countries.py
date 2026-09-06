"""REST Countries v3.1 — anahtarsız, sabit host, kabuk yok.

https://restcountries.com
https://gitlab.com/restcountries/restcountries
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

COUNTRY_HOST = "restcountries.com"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_FIELDS = (
    "name,cca2,cca3,capital,region,subregion,population,area,"
    "currencies,languages,timezones,borders,flags"
)

def country_name_url(query: str) -> str:
    clean = query.strip()
    if not clean:
        raise ToolExecutionError(loc("Ülke adı boş olamaz.", "Country name cannot be empty."))
    return f"https://{COUNTRY_HOST}/v3.1/name/{quote(clean, safe='')}?fields={_FIELDS}"

def country_alpha_url(code: str) -> str:
    token = code.strip().upper()
    if len(token) not in {2, 3} or not token.isalpha():
        raise ToolExecutionError(
            loc("ISO kod 2 veya 3 harf olmalı.", "ISO code must be 2 or 3 letters.")
        )
    return f"https://{COUNTRY_HOST}/v3.1/alpha/{quote(token, safe='')}?fields={_FIELDS}"

def _assert_restcountries(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != COUNTRY_HOST:
        raise ToolExecutionError(
            loc(
                "Ülke isteği yalnızca restcountries.com üzerinde kalır.",
                "Country requests must stay on restcountries.com.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Ülke adresinde kullanıcı bilgisi olamaz.",
                "Country URLs cannot include user info.",
            )
        )
    return url

def _looks_like_iso(query: str) -> bool:
    token = query.strip()
    return len(token) in {2, 3} and token.isalpha()

def _parse_country(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("name") if isinstance(item.get("name"), dict) else {}
    currencies = item.get("currencies") if isinstance(item.get("currencies"), dict) else {}
    languages = item.get("languages") if isinstance(item.get("languages"), dict) else {}
    flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
    capital = item.get("capital") if isinstance(item.get("capital"), list) else []
    return {
        "name": str(name.get("common") or name.get("official") or "")[:200],
        "official": str(name.get("official") or "")[:240],
        "cca2": str(item.get("cca2") or "")[:8],
        "cca3": str(item.get("cca3") or "")[:8],
        "capital": [str(city)[:80] for city in capital[:4]],
        "region": str(item.get("region") or "")[:80],
        "subregion": str(item.get("subregion") or "")[:80],
        "population": item.get("population"),
        "area_km2": item.get("area"),
        "currencies": list(currencies.keys())[:8],
        "languages": [str(label)[:80] for label in languages.values()][:8],
        "timezones": [str(zone)[:40] for zone in (item.get("timezones") or [])][:8],
        "borders": [str(code)[:8] for code in (item.get("borders") or [])][:16],
        "flag": str(flags.get("png") or flags.get("svg") or "")[:2000],
    }

async def lookup_country(query: str) -> dict[str, Any]:
    """Ada veya ISO koda göre ülke kaydı."""
    clean = query.strip()
    if not clean:
        raise ToolExecutionError(loc("Ülke adı boş olamaz.", "Country name cannot be empty."))
    url = _assert_restcountries(
        country_alpha_url(clean) if _looks_like_iso(clean) else country_name_url(clean)
    )
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Ülke API yönlendirmesi kabul edilmez.",
                        "Country API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "query": clean,
                    "reason": loc(
                        "Ülke bulunamadı. wiki_lookup dene.",
                        "Country not found. Try wiki_lookup.",
                    ),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Ülke bilgisi alınamadı: {exc}", f"Could not fetch country info: {exc}")
        ) from exc

    rows: list[dict[str, Any]]
    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        rows = [payload]
    else:
        raise ToolExecutionError(loc("Ülke yanıtı geçersiz.", "Country response is invalid."))
    countries = [_parse_country(item) for item in rows[:5]]
    return {
        "ok": True,
        "found": bool(countries),
        "query": clean,
        "count": len(countries),
        "countries": countries,
        "source": COUNTRY_HOST,
    }
