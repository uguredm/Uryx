"""Open-Meteo hava kalitesi — anahtarsız, sabit host, kabuk yok.

https://open-meteo.com/en/docs/air-quality-api
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc
from app.services.web.weather import GEO_HOST, geocode_url

AQ_HOST = "air-quality-api.open-meteo.com"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def _eaqi_label(value: object) -> str:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return loc("bilinmiyor", "unknown")
    if score <= 20:
        return loc("iyi", "good")
    if score <= 40:
        return loc("uygun", "fair")
    if score <= 60:
        return loc("orta", "moderate")
    if score <= 80:
        return loc("zayıf", "poor")
    if score <= 100:
        return loc("çok zayıf", "very poor")
    return loc("aşırı kötü", "extremely poor")

def air_quality_url(lat: float, lon: float) -> str:
    return (
        f"https://{AQ_HOST}/v1/air-quality?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone"
        "&timezone=Europe%2FIstanbul"
    )

def _assert_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ToolExecutionError(
            loc(
                f"Hava kalitesi isteği yalnızca {host} üzerinde kalır.",
                f"Air quality requests must stay on {host}.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Hava kalitesi adresinde kullanıcı bilgisi olamaz.",
                "Air quality URLs cannot include user info.",
            )
        )
    return url

async def lookup_air_quality(place: str) -> dict[str, Any]:
    """Yer adını geocode eder; güncel AQI/PM döndürür."""
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
                        "Hava kalitesi yönlendirmesi kabul edilmez.",
                        "Air quality redirects are not accepted.",
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
            aq_resp = await client.get(_assert_host(air_quality_url(lat, lon), AQ_HOST))
            if aq_resp.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Hava kalitesi yönlendirmesi kabul edilmez.",
                        "Air quality redirects are not accepted.",
                    )
                )
            aq_resp.raise_for_status()
            payload = aq_resp.json()
    except ToolExecutionError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(f"Hava kalitesi alınamadı: {exc}", f"Could not fetch air quality: {exc}")
        ) from exc

    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise ToolExecutionError(
            loc("Hava kalitesi yanıtı geçersiz.", "Air quality response is invalid.")
        )
    eaqi = current.get("european_aqi")
    return {
        "ok": True,
        "place": str(hit.get("name") or clean)[:200],
        "country": str(hit.get("country") or "")[:80],
        "latitude": lat,
        "longitude": lon,
        "european_aqi": eaqi,
        "quality": _eaqi_label(eaqi),
        "pm10": current.get("pm10"),
        "pm2_5": current.get("pm2_5"),
        "no2": current.get("nitrogen_dioxide"),
        "ozone": current.get("ozone"),
        "observed_at": str(current.get("time") or "")[:32],
        "source": "open-meteo.com/air-quality",
    }
