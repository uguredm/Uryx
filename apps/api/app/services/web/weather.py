"""Open-Meteo hava — anahtarsız, sabit host, kabuk yok.

https://open-meteo.com/en/docs
https://open-meteo.com/en/docs/geocoding-api
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc, ui_language

GEO_HOST = "geocoding-api.open-meteo.com"
WX_HOST = "api.open-meteo.com"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_WMO = {
    0: "açık",
    1: "çoğunlukla açık",
    2: "parçalı bulutlu",
    3: "kapalı",
    45: "sis",
    48: "kırağılı sis",
    51: "hafif çisenti",
    61: "hafif yağmur",
    63: "yağmur",
    65: "şiddetli yağmur",
    71: "hafif kar",
    73: "kar",
    75: "şiddetli kar",
    80: "sağanak",
    95: "gök gürültülü fırtına",
}

_WMO_EN = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "showers",
    95: "thunderstorm",
}

def _wmo_label(code: int) -> str:
    tr = _WMO.get(code)
    en = _WMO_EN.get(code)
    if tr and en:
        return loc(tr, en)
    return loc(f"kod {code}", f"code {code}")

def _assert_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ToolExecutionError(
            loc(
                f"Hava isteği yalnızca {host} üzerinde kalır.",
                f"Weather requests must stay on {host}.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("Hava adresinde kullanıcı bilgisi olamaz.", "Weather URLs cannot include user info.")
        )
    return url

def geocode_url(place: str) -> str:
    clean = place.strip()
    if not clean:
        raise ToolExecutionError(loc("Yer adı boş olamaz.", "Place name cannot be empty."))
    lang = "tr" if ui_language() == "tr" else "en"
    return f"https://{GEO_HOST}/v1/search?name={quote(clean)}&count=1&language={lang}&format=json"

def normalize_forecast_days(value: object) -> int:
    try:
        days = int(value or 3)
    except (TypeError, ValueError):
        days = 3
    return max(1, min(days, 7))

def forecast_url(lat: float, lon: float, *, days: int = 3) -> str:
    window = normalize_forecast_days(days)
    return (
        f"https://{WX_HOST}/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m,precipitation"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&forecast_days={window}"
        "&timezone=Europe%2FIstanbul"
    )

def parse_daily_forecast(payload: dict[str, Any]) -> list[dict[str, Any]]:
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        return []
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    rain = daily.get("precipitation_sum") or []
    rows: list[dict[str, Any]] = []
    for index, date in enumerate(dates):
        code = int(codes[index]) if index < len(codes) and codes[index] is not None else 0
        rows.append(
            {
                "date": str(date)[:16],
                "condition": _wmo_label(code),
                "tmax_c": highs[index] if index < len(highs) else None,
                "tmin_c": lows[index] if index < len(lows) else None,
                "precipitation_mm": rain[index] if index < len(rain) else None,
            }
        )
    return rows

async def lookup_weather(place: str, *, days: int = 3) -> dict[str, Any]:
    """Yer adını geocode eder; güncel + günlük tahmini döndürür."""
    clean = place.strip()
    if not clean:
        raise ToolExecutionError(loc("Yer adı boş olamaz.", "Place name cannot be empty."))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            geo = await _get_json(client, _assert_host(geocode_url(clean), GEO_HOST))
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
            window = normalize_forecast_days(days)
            wx = await _get_json(
                client, _assert_host(forecast_url(lat, lon, days=window), WX_HOST)
            )
    except ToolExecutionError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            loc(f"Hava durumu alınamadı: {exc}", f"Could not fetch weather: {exc}")
        ) from exc

    current = wx.get("current") if isinstance(wx, dict) else None
    if not isinstance(current, dict):
        raise ToolExecutionError(loc("Hava yanıtı geçersiz.", "Weather response is invalid."))
    code = int(current.get("weather_code") or 0)
    return {
        "ok": True,
        "place": str(hit.get("name") or clean)[:200],
        "country": str(hit.get("country") or "")[:80],
        "latitude": lat,
        "longitude": lon,
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "precipitation_mm": current.get("precipitation"),
        "condition": _wmo_label(code),
        "observed_at": str(current.get("time") or "")[:32],
        "days": normalize_forecast_days(days),
        "daily": parse_daily_forecast(wx if isinstance(wx, dict) else {}),
        "source": "open-meteo.com",
        "timezone": "Europe/Istanbul",
    }

async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    response = await client.get(url)
    if response.status_code in {301, 302, 303, 307, 308}:
        raise ToolExecutionError(
            loc("Hava API yönlendirmesi kabul edilmez.", "Weather API redirects are not accepted.")
        )
    response.raise_for_status()
    return response.json()
