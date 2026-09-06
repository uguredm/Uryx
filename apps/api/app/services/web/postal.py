"""Zippopotam.us posta kodu — anahtarsız, sabit host, kabuk yok.

https://docs.zippopotam.us/
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

POSTAL_HOST = "api.zippopotam.us"
POSTAL_COUNTRIES = frozenset({"TR", "DE", "US", "GB", "FR", "NL", "AT", "BE", "IT", "ES"})
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{1,11}$")

def normalize_postal_country(value: str | None) -> str:
    token = (value or "TR").strip().upper()
    aliases = {"TUR": "TR", "UK": "GB", "USA": "US", "GER": "DE"}
    token = aliases.get(token, token)
    if token not in POSTAL_COUNTRIES:
        raise ToolExecutionError(
            loc(
                "Ülke kodu desteklenmiyor. "
                f"İzinli: {', '.join(sorted(POSTAL_COUNTRIES))}.",
                "Unsupported country code. "
                f"Allowed: {', '.join(sorted(POSTAL_COUNTRIES))}.",
            )
        )
    return token

def normalize_postal_code(value: str) -> str:
    token = (value or "").strip()
    if not _CODE_RE.match(token):
        raise ToolExecutionError(
            loc(
                "Posta kodu 2–12 karakter, harf/rakam olmalı.",
                "Postal code must be 2–12 characters of letters or digits.",
            )
        )
    return token.replace(" ", "")

def postal_url(code: str, *, country: str = "TR") -> str:
    iso = normalize_postal_country(country).lower()
    clean = normalize_postal_code(code)
    return f"https://{POSTAL_HOST}/{iso}/{quote(clean, safe='')}"

def _assert_zippo(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != POSTAL_HOST:
        raise ToolExecutionError(
            loc(
                "Posta isteği yalnızca api.zippopotam.us üzerinde kalır.",
                "Postal requests must stay on api.zippopotam.us.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Posta adresinde kullanıcı bilgisi olamaz.",
                "Postal URLs cannot include user info.",
            )
        )
    return url

def _parse_places(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (payload.get("places") or [])[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "place": str(item.get("place name") or "")[:120],
                "state": str(item.get("state") or "")[:120],
                "state_code": str(item.get("state abbreviation") or "")[:16],
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            }
        )
    return rows

async def lookup_postal(code: str, *, country: str = "TR") -> dict[str, Any]:
    """Posta kodunu yer adına çözer."""
    url = _assert_zippo(postal_url(code, country=country))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Posta API yönlendirmesi kabul edilmez.",
                        "Postal API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "code": normalize_postal_code(code),
                    "country": normalize_postal_country(country),
                    "reason": loc("Posta kodu bulunamadı.", "Postal code not found."),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Posta kodu alınamadı: {exc}", f"Could not fetch postal code: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("Posta yanıtı geçersiz.", "Postal response is invalid."))
    places = _parse_places(payload)
    return {
        "ok": True,
        "found": bool(places),
        "code": str(payload.get("post code") or normalize_postal_code(code))[:16],
        "country": str(payload.get("country") or "")[:80],
        "country_code": normalize_postal_country(country),
        "places": places,
        "source": POSTAL_HOST,
    }
