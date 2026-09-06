"""USGS deprem kataloğu — anahtarsız, sabit host, kabuk yok.

https://earthquake.usgs.gov/fdsnws/event/1/
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

USGS_HOST = "earthquake.usgs.gov"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_TR_BOX = {
    "minlatitude": "35.8",
    "maxlatitude": "42.4",
    "minlongitude": "25.6",
    "maxlongitude": "45.0",
}
_REGIONS = frozenset({"tr", "world"})

def _istanbul_now() -> datetime:
    try:
        zone: timezone | ZoneInfo = ZoneInfo("Europe/Istanbul")
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=3), name="Europe/Istanbul")
    return datetime.now(zone)

def normalize_quake_region(value: str | None) -> str:
    token = (value or "tr").strip().casefold()
    aliases = {
        "turkey": "tr",
        "turkiye": "tr",
        "türkiye": "tr",
        "global": "world",
        "worldwide": "world",
        "dunya": "world",
        "dünya": "world",
    }
    token = aliases.get(token, token)
    if token not in _REGIONS:
        raise ToolExecutionError(
            loc("Bölge tr veya world olmalı.", "Region must be tr or world.")
        )
    return token

def normalize_quake_days(value: object) -> int:
    try:
        days = int(value) if value not in (None, "") else 2
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc("Gün sayısı 1–7 arasında olmalı.", "Day count must be between 1 and 7.")
        ) from exc
    if days < 1 or days > 7:
        raise ToolExecutionError(
            loc("Gün sayısı 1–7 arasında olmalı.", "Day count must be between 1 and 7.")
        )
    return days

def normalize_min_magnitude(value: object, *, region: str) -> float:
    default = 3.0 if region == "tr" else 5.0
    try:
        mag = float(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc("Büyüklük 1–10 arasında olmalı.", "Magnitude must be between 1 and 10.")
        ) from exc
    if mag < 1 or mag > 10:
        raise ToolExecutionError(
            loc("Büyüklük 1–10 arasında olmalı.", "Magnitude must be between 1 and 10.")
        )
    return mag

def normalize_quake_limit(value: object) -> int:
    try:
        limit = int(value) if value not in (None, "") else 8
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc("Limit 1–15 arasında olmalı.", "Limit must be between 1 and 15.")
        ) from exc
    if limit < 1 or limit > 15:
        raise ToolExecutionError(
            loc("Limit 1–15 arasında olmalı.", "Limit must be between 1 and 15.")
        )
    return limit

def earthquakes_url(
    *,
    region: str = "tr",
    minmagnitude: float | None = None,
    days: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> str:
    area = normalize_quake_region(region)
    mag = normalize_min_magnitude(minmagnitude, region=area)
    window = normalize_quake_days(days)
    cap = normalize_quake_limit(limit)
    start = ((now or _istanbul_now()) - timedelta(days=window)).date().isoformat()
    params: dict[str, str] = {
        "format": "geojson",
        "orderby": "time",
        "starttime": start,
        "minmagnitude": f"{mag:g}",
        "limit": str(cap),
    }
    if area == "tr":
        params.update(_TR_BOX)
    return f"https://{USGS_HOST}/fdsnws/event/1/query?{urlencode(params)}"

def _assert_usgs(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != USGS_HOST:
        raise ToolExecutionError(
            loc(
                "Deprem isteği yalnızca earthquake.usgs.gov üzerinde kalır.",
                "Earthquake requests must stay on earthquake.usgs.gov.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Deprem adresinde kullanıcı bilgisi olamaz.",
                "Earthquake URLs cannot include user info.",
            )
        )
    return url

def _parse_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    features = payload.get("features")
    if not isinstance(features, list):
        return []
    events: list[dict[str, Any]] = []
    for item in features[:15]:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        geom = item.get("geometry") if isinstance(item.get("geometry"), dict) else {}
        coords = geom.get("coordinates") if isinstance(geom.get("coordinates"), list) else []
        depth = coords[2] if len(coords) > 2 and isinstance(coords[2], int | float) else None
        when_ms = props.get("time")
        when = ""
        if isinstance(when_ms, int | float):
            when = datetime.fromtimestamp(when_ms / 1000, tz=UTC).isoformat()
        events.append(
            {
                "magnitude": props.get("mag"),
                "place": str(props.get("place") or "")[:240],
                "time_utc": when[:32],
                "depth_km": depth,
                "tsunami": bool(props.get("tsunami")),
                "url": str(props.get("url") or "")[:2000],
            }
        )
    return events

async def lookup_earthquakes(
    *,
    region: str = "tr",
    minmagnitude: float | None = None,
    days: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Son günlerin depremlerini USGS kataloğundan okur."""
    area = normalize_quake_region(region)
    mag = normalize_min_magnitude(minmagnitude, region=area)
    window = normalize_quake_days(days)
    cap = normalize_quake_limit(limit)
    url = _assert_usgs(
        earthquakes_url(region=area, minmagnitude=mag, days=window, limit=cap)
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
                        "Deprem API yönlendirmesi kabul edilmez.",
                        "Earthquake API redirects are not accepted.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Deprem listesi alınamadı: {exc}", f"Could not fetch earthquake list: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(
            loc("Deprem yanıtı geçersiz.", "Earthquake response is invalid.")
        )
    events = _parse_events(payload)
    return {
        "ok": True,
        "region": area,
        "minmagnitude": mag,
        "days": window,
        "count": len(events),
        "events": events,
        "source": USGS_HOST,
    }
