"""Aladhan namaz vakitleri — anahtarsız, sabit host, kabuk yok.

https://aladhan.com/prayer-times-api
Diyanet yöntemi: method=13
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

PRAYER_HOST = "api.aladhan.com"
PRAYER_METHODS = frozenset({13, 3})
PRAYER_COUNTRIES = frozenset({"TR", "DE", "US", "GB", "FR", "NL", "AT", "BE", "SA", "AE"})
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KEEP_TIMES = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")

def _istanbul_now() -> datetime:
    try:
        zone: timezone | ZoneInfo = ZoneInfo("Europe/Istanbul")
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=3), name="Europe/Istanbul")
    return datetime.now(zone)

def normalize_prayer_country(value: str | None) -> str:
    token = (value or "TR").strip().upper()
    aliases = {"TUR": "TR", "TURKIYE": "TR", "UK": "GB", "USA": "US", "GER": "DE"}
    token = aliases.get(token, token)
    if token not in PRAYER_COUNTRIES:
        raise ToolExecutionError(
            loc(
                "Ülke kodu desteklenmiyor. "
                f"İzinli: {', '.join(sorted(PRAYER_COUNTRIES))}.",
                "Unsupported country code. "
                f"Allowed: {', '.join(sorted(PRAYER_COUNTRIES))}.",
            )
        )
    return token

def normalize_prayer_method(value: object) -> int:
    try:
        method = int(value) if value not in (None, "") else 13
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(
                "Hesap yöntemi 13 (Diyanet) veya 3 (MWL) olmalı.",
                "Calculation method must be 13 (Diyanet) or 3 (MWL).",
            )
        ) from exc
    if method not in PRAYER_METHODS:
        raise ToolExecutionError(
            loc(
                "Hesap yöntemi 13 (Diyanet) veya 3 (MWL) olmalı.",
                "Calculation method must be 13 (Diyanet) or 3 (MWL).",
            )
        )
    return method

def normalize_prayer_date(value: str | None) -> str:
    if not value or not str(value).strip():
        return _istanbul_now().date().isoformat()
    token = str(value).strip()
    if not _DATE_RE.match(token):
        raise ToolExecutionError(loc("Tarih YYYY-MM-DD olmalı.", "Date must be YYYY-MM-DD."))
    year = int(token[:4])
    now = _istanbul_now().year
    if year < 2000 or year > now + 1:
        raise ToolExecutionError(
            loc(
                "Tarih 2000 ile (bu yıl+1) arasında olmalı.",
                "Date must be between 2000 and (this year+1).",
            )
        )
    return token

def prayer_times_url(
    city: str, *, country: str = "TR", method: int = 13, date: str | None = None
) -> str:
    clean = city.strip()
    if not clean:
        raise ToolExecutionError(loc("Şehir adı boş olamaz.", "City name cannot be empty."))
    code = normalize_prayer_country(country)
    algo = normalize_prayer_method(method)
    when = normalize_prayer_date(date)
    query = urlencode({"city": clean, "country": code, "method": str(algo)})
    return f"https://{PRAYER_HOST}/v1/timingsByCity/{quote(when, safe='')}?{query}"

def _assert_aladhan(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != PRAYER_HOST:
        raise ToolExecutionError(
            loc(
                "Namaz isteği yalnızca api.aladhan.com üzerinde kalır.",
                "Prayer requests must stay on api.aladhan.com.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Namaz adresinde kullanıcı bilgisi olamaz.",
                "Prayer URLs cannot include user info.",
            )
        )
    return url

def _parse_timings(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    raw = data.get("timings") if isinstance(data.get("timings"), dict) else {}
    date = data.get("date") if isinstance(data.get("date"), dict) else {}
    hijri = date.get("hijri") if isinstance(date.get("hijri"), dict) else {}
    gregorian = date.get("gregorian") if isinstance(date.get("gregorian"), dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    method = meta.get("method") if isinstance(meta.get("method"), dict) else {}
    timings = {
        key.lower(): str(raw.get(key) or "").split(" ", 1)[0][:8] for key in _KEEP_TIMES
    }
    return {
        "ok": True,
        "timings": timings,
        "gregorian": str(gregorian.get("date") or "")[:16],
        "hijri": str(hijri.get("date") or "")[:16],
        "method": str(method.get("name") or "")[:120],
    }

async def lookup_prayer_times(
    city: str,
    *,
    country: str = "TR",
    method: int = 13,
    date: str | None = None,
) -> dict[str, Any]:
    """Diyanet (13) veya MWL (3) ile günlük namaz vakitleri."""
    clean = city.strip()
    if not clean:
        raise ToolExecutionError(loc("Şehir adı boş olamaz.", "City name cannot be empty."))
    url = _assert_aladhan(
        prayer_times_url(clean, country=country, method=method, date=date)
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
                        "Namaz API yönlendirmesi kabul edilmez.",
                        "Prayer API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                raise ToolExecutionError(
                    loc(
                        "Bu şehir için namaz vakti bulunamadı.",
                        "Prayer times were not found for this city.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Namaz vakitleri alınamadı: {exc}", f"Could not fetch prayer times: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("Namaz yanıtı geçersiz.", "Prayer response is invalid."))
    parsed = _parse_timings(payload)
    if not any(parsed["timings"].values()):
        raise ToolExecutionError(loc("Namaz yanıtı geçersiz.", "Prayer response is invalid."))
    return {
        **parsed,
        "city": clean[:120],
        "country": normalize_prayer_country(country),
        "source": PRAYER_HOST,
    }
