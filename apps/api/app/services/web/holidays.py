"""Nager.Date resmi tatil — anahtarsız, sabit host, kabuk yok.

https://date.nager.at/api
https://github.com/nager/Nager.Date
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

HOLIDAY_HOST = "date.nager.at"
HOLIDAY_COUNTRIES = frozenset(
    {
        "TR",
        "DE",
        "US",
        "GB",
        "FR",
        "IT",
        "ES",
        "AT",
        "NL",
        "BE",
        "CH",
        "SE",
        "NO",
        "DK",
        "PL",
        "GR",
        "PT",
        "IE",
        "FI",
        "CZ",
    }
)
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def normalize_holiday_country(value: str | None) -> str:
    token = (value or "TR").strip().upper()
    aliases = {"TUR": "TR", "TURKIYE": "TR", "UK": "GB", "USA": "US", "GER": "DE"}
    token = aliases.get(token, token)
    if token not in HOLIDAY_COUNTRIES:
        raise ToolExecutionError(
            loc(
                "Ülke kodu desteklenmiyor. "
                f"İzinli: {', '.join(sorted(HOLIDAY_COUNTRIES))}.",
                "Unsupported country code. "
                f"Allowed: {', '.join(sorted(HOLIDAY_COUNTRIES))}.",
            )
        )
    return token

def _istanbul_now() -> datetime:
    try:
        zone: timezone | ZoneInfo = ZoneInfo("Europe/Istanbul")
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=3), name="Europe/Istanbul")
    return datetime.now(zone)

def normalize_holiday_year(value: object) -> int:
    now = _istanbul_now().year
    try:
        year = int(value) if value not in (None, "") else now
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(
                "Yıl 2000–2035 arasında bir sayı olmalı.",
                "Year must be a number between 2000 and 2035.",
            )
        ) from exc
    if year < 2000 or year > now + 5:
        raise ToolExecutionError(
            loc(
                "Yıl 2000 ile (bu yıl+5) arasında olmalı.",
                "Year must be between 2000 and (this year+5).",
            )
        )
    return year

def holidays_url(country: str, year: int) -> str:
    return f"https://{HOLIDAY_HOST}/api/v3/PublicHolidays/{year}/{country}"

def _assert_nager(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != HOLIDAY_HOST:
        raise ToolExecutionError(
            loc(
                "Tatil isteği yalnızca date.nager.at üzerinde kalır.",
                "Holiday requests must stay on date.nager.at.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Tatil adresinde kullanıcı bilgisi olamaz.",
                "Holiday URLs cannot include user info.",
            )
        )
    return url

async def lookup_public_holidays(
    *, country: str = "TR", year: int | None = None
) -> dict[str, Any]:
    """Bir yılın resmi tatillerini döndürür."""
    code = normalize_holiday_country(country)
    when = normalize_holiday_year(year)
    url = _assert_nager(holidays_url(code, when))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Tatil API yönlendirmesi kabul edilmez.",
                        "Holiday API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                raise ToolExecutionError(
                    loc(
                        "Bu ülke/yıl için tatil listesi yok.",
                        "No holiday list exists for this country/year.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Resmi tatil listesi alınamadı: {exc}", f"Could not fetch public holidays: {exc}")
        ) from exc

    if not isinstance(payload, list):
        raise ToolExecutionError(loc("Tatil yanıtı geçersiz.", "Holiday response is invalid."))
    holidays: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        holidays.append(
            {
                "date": str(item.get("date") or "")[:16],
                "local_name": str(item.get("localName") or item.get("name") or "")[:200],
                "name": str(item.get("name") or "")[:200],
                "global": bool(item.get("global", True)),
                "types": [str(kind) for kind in (item.get("types") or [])][:8],
            }
        )
    return {
        "ok": True,
        "country": code,
        "year": when,
        "count": len(holidays),
        "holidays": holidays,
        "source": "date.nager.at",
    }
