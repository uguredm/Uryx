"""Frankfurter döviz kuru — anahtarsız, sabit host, kabuk yok.

https://frankfurter.dev/  ·  https://api.frankfurter.dev/v2/rate/USD/TRY
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

FX_HOST = "api.frankfurter.dev"

FX_CODES = frozenset(
    {
        "USD",
        "EUR",
        "TRY",
        "GBP",
        "JPY",
        "CHF",
        "CAD",
        "AUD",
        "CNY",
        "SEK",
        "NOK",
        "DKK",
        "PLN",
        "INR",
        "KRW",
        "BRL",
        "MXN",
        "SGD",
        "HKD",
        "NZD",
    }
)
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def normalize_fx_code(value: str | None) -> str:
    token = (value or "").strip().upper().replace("TL", "TRY")
    if token == "YEN":
        token = "JPY"
    if token not in FX_CODES:
        raise ToolExecutionError(
            loc(
                "Döviz kodu desteklenmiyor. "
                f"İzinli: {', '.join(sorted(FX_CODES))}.",
                "Unsupported currency code. "
                f"Allowed: {', '.join(sorted(FX_CODES))}.",
            )
        )
    return token

def fx_rate_url(base: str, quote: str) -> str:
    return f"https://{FX_HOST}/v2/rate/{base}/{quote}"

def _assert_frankfurter(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != FX_HOST:
        raise ToolExecutionError(
            loc(
                "Döviz isteği yalnızca api.frankfurter.dev üzerinde kalır.",
                "FX requests must stay on api.frankfurter.dev.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("Döviz adresinde kullanıcı bilgisi olamaz.", "FX URLs cannot include user info.")
        )
    return url

async def lookup_fx_rate(
    *,
    base: str,
    quote: str,
    amount: float = 1.0,
) -> dict[str, Any]:
    """Tek çift kur + isteğe bağlı tutar çevirisi."""
    from_code = normalize_fx_code(base)
    to_code = normalize_fx_code(quote)
    if from_code == to_code:
        raise ToolExecutionError(
            loc("Kaynak ve hedef döviz aynı olamaz.", "Base and quote currencies cannot be the same.")
        )
    try:
        qty = float(amount)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(loc("Tutar sayı olmalı.", "Amount must be a number.")) from exc
    if qty <= 0 or qty > 1e12:
        raise ToolExecutionError(
            loc("Tutar 0 ile 1e12 arasında olmalı.", "Amount must be between 0 and 1e12.")
        )

    url = _assert_frankfurter(fx_rate_url(from_code, to_code))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Döviz API yönlendirmesi kabul edilmez.",
                        "FX API redirects are not accepted.",
                    )
                )
            if response.status_code == 422:
                raise ToolExecutionError(
                    loc(
                        "Frankfurter bu döviz çiftini bilmiyor.",
                        "Frankfurter does not know this currency pair.",
                    )
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Döviz kuru alınamadı: {exc}", f"Could not fetch FX rate: {exc}")
        ) from exc

    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("Döviz yanıtı geçersiz.", "FX response is invalid."))
    rate = payload.get("rate")
    try:
        rate_f = float(rate)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(loc("Döviz kuru sayı değil.", "FX rate is not a number.")) from exc
    converted = round(qty * rate_f, 6)
    return {
        "ok": True,
        "base": from_code,
        "quote": to_code,
        "rate": rate_f,
        "amount": qty,
        "converted": converted,
        "date": str(payload.get("date") or "")[:16],
        "source": "frankfurter.dev",
        "provider": "ECB-blend",
    }
