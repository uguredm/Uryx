"""Open-Meteo gün doğumu / UV — weather'dan ayrı, sabit host, kabuk yok.

https://open-meteo.com/en/docs
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc
from app.services.web.weather import GEO_HOST, WX_HOST, geocode_url

_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def _uv_label(value: object) -> str:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return loc("bilinmiyor", "unknown")
    if score < 3:
        return loc("düşük", "low")
    if score < 6:
        return loc("orta", "moderate")
    if score < 8:
        return loc("yüksek", "high")
    if score < 11:
        return loc("çok yüksek", "very high")
    return loc("aşırı", "extreme")

def normalize_sun_days(value: object) -> int:
    try:
        days = int(value or 1)
    except (TypeError, ValueError):
        days = 1
    return max(1, min(days, 3))

def sun_times_url(lat: float, lon: float, *, days: int = 1) -> str:
    window = normalize_sun_days(days)
    return (
        f"https://{WX_HOST}/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
        "&daily=sunrise,sunset,uv_index_max"
        f"&forecast_days={window}"
        "&timezone=Europe%2FIstanbul"
    )

def _assert_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ToolExecutionError(
            loc(
                f"Güneş isteği yalnızca {host} üzerinde kalır.",
                f"Sun requests must stay on {host}.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("Güneş adresinde kullanıcı bilgisi olamaz.", "Sun URLs cannot include user info.")
        )
    return url

def parse_sun_days(payload: dict[str, Any]) -> list[dict[str, Any]]:
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        return []
    dates = daily.get("time") or []
    rises = daily.get("sunrise") or []
    sets = daily.get("sunset") or []
    uvs = daily.get("uv_index_max") or []
    rows: list[dict[str, Any]] = []
    for index, date in enumerate(dates):
        uv = uvs[index] if index < len(uvs) else None
        rows.append(
            {
                "date": str(date)[:16],
                "sunrise": str(rises[index] if index < len(rises) else "")[:32],
                "sunset": str(sets[index] if index < len(sets) else "")[:32],
                "uv_index_max": uv,
                "uv_label": _uv_label(uv),
            }
        )
    return rows

async def lookup_sun_times(place: str, *, days: int = 1) -> dict[str, Any]:
    """Yer adı → gün doğumu/batımı ve günlük UV tavanı."""
    clean = place.strip()
    if not clean:
        raise ToolExecutionError(loc("Yer adı boş olamaz.", "Place name cannot be empty."))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            geo_resp = await client.get(_assert_host(geocode_url(clean), GEO_HOST))
            if geo_resp.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Güneş API yönlendirmesi kabul edilmez.",
                        "Sun API redirects are not accepted.",
                    )
                )
            geo_resp.raise_for_status()
            geo = geo_resp.json()
            results = geo.get("results") if isinstance(geo, dict) else None
            if not results:
                raise ToolExecutionError(
                    loc(
                        f"'{clean}' için konum bulunamadı.",
                        f"No location found for '{clean}'.",
                    )
                )
            hit = results[0]
            lat = float(hit["latitude"])
            lon = float(hit["longitude"])
            window = normalize_sun_days(days)
            sun_resp = await client.get(
                _assert_host(sun_times_url(lat, lon, days=window), WX_HOST)
            )
            if sun_resp.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Güneş API yönlendirmesi kabul edilmez.",
                        "Sun API redirects are not accepted.",
                    )
                )
            sun_resp.raise_for_status()
            payload = sun_resp.json()
    except ToolExecutionError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(f"Gün doğumu bilgisi alınamadı: {exc}", f"Could not fetch sunrise data: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("Güneş yanıtı geçersiz.", "Sun response is invalid."))
    days_out = parse_sun_days(payload)
    today = days_out[0] if days_out else {}
    return {
        "ok": True,
        "place": str(hit.get("name") or clean)[:200],
        "country": str(hit.get("country") or "")[:80],
        "days": window,
        "sunrise": today.get("sunrise"),
        "sunset": today.get("sunset"),
        "uv_index_max": today.get("uv_index_max"),
        "uv_label": today.get("uv_label"),
        "daily": days_out,
        "source": "open-meteo.com",
        "timezone": "Europe/Istanbul",
    }
