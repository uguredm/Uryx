"""Open-Meteo yükseklik — weather rewrite yok, sabit host, kabuk yok.

https://open-meteo.com/en/docs/elevation-api
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc
from app.services.web.weather import GEO_HOST, WX_HOST, geocode_url

_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def elevation_url(lat: float, lon: float) -> str:
    return f"https://{WX_HOST}/v1/elevation?latitude={lat:.4f}&longitude={lon:.4f}"

def _assert_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ToolExecutionError(
            loc(
                f"Yükseklik isteği yalnızca {host} üzerinde kalır.",
                f"Elevation requests must stay on {host}.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Yükseklik adresinde kullanıcı bilgisi olamaz.",
                "Elevation URLs cannot include user info.",
            )
        )
    return url

async def lookup_elevation(place: str) -> dict[str, Any]:
    """Yer adı → DEM rakımı (metre)."""
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
                        "Yükseklik yönlendirmesi kabul edilmez.",
                        "Elevation redirects are not accepted.",
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
            el_resp = await client.get(_assert_host(elevation_url(lat, lon), WX_HOST))
            if el_resp.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Yükseklik yönlendirmesi kabul edilmez.",
                        "Elevation redirects are not accepted.",
                    )
                )
            el_resp.raise_for_status()
            payload = el_resp.json()
    except ToolExecutionError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(f"Yükseklik alınamadı: {exc}", f"Could not fetch elevation: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(
            loc("Yükseklik yanıtı geçersiz.", "Elevation response is invalid.")
        )
    values = payload.get("elevation") if isinstance(payload.get("elevation"), list) else []
    meters = values[0] if values else None
    return {
        "ok": True,
        "place": str(hit.get("name") or clean)[:200],
        "country": str(hit.get("country") or "")[:80],
        "latitude": lat,
        "longitude": lon,
        "elevation_m": meters,
        "source": "open-meteo.com",
    }
