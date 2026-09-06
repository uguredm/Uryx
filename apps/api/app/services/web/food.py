"""Open Food Facts barkod — anahtarsız, sabit host, kabuk yok.

https://world.openfoodfacts.org/data
Yönlendirme yok (beauty/pet sunucularına 302 reddedilir).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

FOOD_HOST = "world.openfoodfacts.org"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_BARCODE_RE = re.compile(r"^\d{8,14}$")
_FIELDS = "product_name,brands,quantity,nutriscore_grade,nova_group,allergens_tags"

def normalize_barcode(value: str) -> str:
    token = re.sub(r"\s+", "", (value or "").strip())
    if not _BARCODE_RE.match(token):
        raise ToolExecutionError(
            loc("Barkod 8–14 rakam olmalı.", "Barcode must be 8–14 digits.")
        )
    return token

def food_barcode_url(barcode: str) -> str:
    code = normalize_barcode(barcode)
    return (
        f"https://{FOOD_HOST}/api/v2/product/{quote(code, safe='')}.json"
        f"?fields={_FIELDS}&lc=tr"
    )

def _assert_food(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != FOOD_HOST:
        raise ToolExecutionError(
            loc(
                "Barkod isteği yalnızca world.openfoodfacts.org üzerinde kalır.",
                "Barcode requests must stay on world.openfoodfacts.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Barkod adresinde kullanıcı bilgisi olamaz.",
                "Barcode URLs cannot include user info.",
            )
        )
    return url

async def lookup_food_barcode(barcode: str) -> dict[str, Any]:
    """EAN/UPC barkodundan ürün adı ve Nutri-Score."""
    url = _assert_food(food_barcode_url(barcode))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc(
                        "Barkod API yönlendirmesi kabul edilmez.",
                        "Barcode API redirects are not accepted.",
                    )
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "barcode": normalize_barcode(barcode),
                    "reason": loc("Ürün bulunamadı.", "Product not found."),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"Ürün bilgisi alınamadı: {exc}", f"Could not fetch product info: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("Ürün yanıtı geçersiz.", "Product response is invalid."))
    product = payload.get("product") if isinstance(payload.get("product"), dict) else {}
    if int(payload.get("status") or 0) != 1 or not product:
        return {
            "ok": True,
            "found": False,
            "barcode": normalize_barcode(barcode),
            "reason": loc("Ürün bulunamadı.", "Product not found."),
        }
    allergens = [
        str(tag).removeprefix("en:")[:80]
        for tag in (product.get("allergens_tags") or [])[:12]
        if isinstance(tag, str)
    ]
    return {
        "ok": True,
        "found": True,
        "barcode": normalize_barcode(barcode),
        "name": str(product.get("product_name") or "")[:200],
        "brands": str(product.get("brands") or "")[:160],
        "quantity": str(product.get("quantity") or "")[:80],
        "nutriscore": str(product.get("nutriscore_grade") or "")[:8],
        "nova_group": product.get("nova_group"),
        "allergens": allergens,
        "source": FOOD_HOST,
    }
