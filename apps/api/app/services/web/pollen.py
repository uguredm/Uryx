"""Open-Meteo polen — air_quality rewrite yok, sabit host, kabuk yok.

https://open-meteo.com/en/docs/air-quality-api
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc
from app.services.web.weather import GEO_HOST, geocode_url

POLLEN_HOST = "air-quality-api.open-meteo.com"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_FIELDS = (
    "alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen"
)

def pollen_url(lat: float, lon: float) -> str:
    return (
        f"https://{POLLEN_HOST}/v1/air-quality?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&current={_FIELDS}&timezone=Europe%2FIstanbul"
    )

def _assert_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ToolExecutionError(
            loc(
                f"Polen isteği yalnızca {host} üzerinde kalır.",
                f"Pollen requests must stay on {host}.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("Polen adresinde kullanıcı bilgisi olamaz.", "Pollen URLs cannot include user info.")
        )
    return url

async def lookup_pollen(place: str) -> dict[str, Any]:
    """Yer adı → güncel polen yoğunlukları (CAMS)."""
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
                    loc("Polen yönlendirmesi kabul edilmez.", "Pollen redirects are not accepted.")
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
            pol_resp = await client.get(_assert_host(pollen_url(lat, lon), POLLEN_HOST))
            if pol_resp.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc("Polen yönlendirmesi kabul edilmez.", "Pollen redirects are not accepted.")
                )
            pol_resp.raise_for_status()
            payload = pol_resp.json()
    except ToolExecutionError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(f"Polen bilgisi alınamadı: {exc}", f"Could not fetch pollen data: {exc}")
        ) from exc
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise ToolExecutionError(loc("Polen yanıtı geçersiz.", "Pollen response is invalid."))
    return {
        "ok": True,
        "place": str(hit.get("name") or clean)[:200],
        "country": str(hit.get("country") or "")[:80],
        "alder": current.get("alder_pollen"),
        "birch": current.get("birch_pollen"),
        "grass": current.get("grass_pollen"),
        "mugwort": current.get("mugwort_pollen"),
        "olive": current.get("olive_pollen"),
        "ragweed": current.get("ragweed_pollen"),
        "observed_at": str(current.get("time") or "")[:32],
        "unit": "grains/m³",
        "source": POLLEN_HOST,
    }
