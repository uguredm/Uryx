"""NOAA SWPC uzay havası — anahtarsız, sabit host, kabuk yok.

https://www.swpc.noaa.gov/content/data-access
https://services.swpc.noaa.gov/products/noaa-scales.json
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

SWPC_HOST = "services.swpc.noaa.gov"
SWPC_SCALES_URL = f"https://{SWPC_HOST}/products/noaa-scales.json"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def space_weather_url() -> str:
    return SWPC_SCALES_URL

def _assert_swpc(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != SWPC_HOST:
        raise ToolExecutionError(
            loc(
                "Uzay havası isteği yalnızca services.swpc.noaa.gov üzerinde kalır.",
                "Space weather requests must stay on services.swpc.noaa.gov.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Uzay havası adresinde kullanıcı bilgisi olamaz.",
                "Space weather URLs cannot include user info.",
            )
        )
    return url

def _scale_block(item: dict[str, Any], key: str) -> dict[str, Any]:
    raw = item.get(key) if isinstance(item.get(key), dict) else {}
    return {
        "scale": str(raw.get("Scale") or raw.get("scale") or "")[:8],
        "text": str(raw.get("Text") or raw.get("text") or "")[:80],
    }

def _parse_slot(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    return {
        "date": str(item.get("DateStamp") or item.get("date") or "")[:16],
        "time": str(item.get("TimeStamp") or item.get("time") or "")[:16],
        "radio_blackout": _scale_block(item, "R"),
        "solar_radiation": _scale_block(item, "S"),
        "geomagnetic": _scale_block(item, "G"),
    }

async def lookup_space_weather() -> dict[str, Any]:
    """NOAA R/S/G ölçeklerini (şimdi / 24s / tahmin) okur."""
    url = _assert_swpc(space_weather_url())
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Uzay havası yönlendirmesi kabul edilmez.",
                        "Space weather redirects are not accepted.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Uzay havası alınamadı: {exc}", f"Could not fetch space weather: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(
            loc("Uzay havası yanıtı geçersiz.", "Space weather response is invalid.")
        )
    return {
        "ok": True,
        "current": _parse_slot(payload.get("0")),
        "observed_24h": _parse_slot(payload.get("-1")),
        "forecast": _parse_slot(payload.get("1")),
        "source": SWPC_HOST,
    }
