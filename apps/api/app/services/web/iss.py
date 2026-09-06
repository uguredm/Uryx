"""ISS konumu — Where the ISS at, anahtarsız, sabit host, kabuk yok.

https://wheretheiss.at/w/developer
https://api.wheretheiss.at/v1/satellites/25544
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

ISS_HOST = "api.wheretheiss.at"
ISS_NORAD_ID = 25544
ISS_URL = f"https://{ISS_HOST}/v1/satellites/{ISS_NORAD_ID}"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def iss_now_url() -> str:
    return ISS_URL

def _assert_iss(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != ISS_HOST:
        raise ToolExecutionError(
            loc(
                "ISS isteği yalnızca api.wheretheiss.at üzerinde kalır.",
                "ISS requests must stay on api.wheretheiss.at.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("ISS adresinde kullanıcı bilgisi olamaz.", "ISS URLs cannot include user info.")
        )
    return url

async def lookup_iss_now() -> dict[str, Any]:
    """ISS'in anlık enlem/boylam/irtifa bilgisini okur."""
    url = _assert_iss(iss_now_url())
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "ISS API yönlendirmesi kabul edilmez.",
                        "ISS API redirects are not accepted.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"ISS konumu alınamadı: {exc}", f"Could not fetch ISS location: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("ISS yanıtı geçersiz.", "ISS response is invalid."))
    stamp = payload.get("timestamp")
    when = ""
    if isinstance(stamp, int | float):
        when = datetime.fromtimestamp(float(stamp), tz=UTC).isoformat()
    return {
        "ok": True,
        "name": str(payload.get("name") or "iss")[:40],
        "norad_id": ISS_NORAD_ID,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "altitude_km": payload.get("altitude"),
        "velocity_kmh": payload.get("velocity"),
        "visibility": str(payload.get("visibility") or "")[:40],
        "observed_at": when[:32],
        "source": ISS_HOST,
    }
