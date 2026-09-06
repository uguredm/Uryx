"""ipwho.is genel IP konumu — anahtarsız, sabit host, kabuk yok.

https://ipwhois.io/documentation
Özel/yerel IP yok; sunucu IP'si sorgulanmaz.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

IPWHO_HOST = "ipwho.is"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"

def normalize_public_ip(value: str) -> str:
    token = (value or "").strip()
    try:
        addr = ipaddress.ip_address(token)
    except ValueError as exc:
        raise ToolExecutionError(
            loc(
                "Geçerli bir IPv4/IPv6 adresi gerekli.",
                "A valid IPv4 or IPv6 address is required.",
            )
        ) from exc
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        raise ToolExecutionError(
            loc("Özel veya yerel IP sorgulanamaz.", "Private or local IPs cannot be queried.")
        )
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        raise ToolExecutionError(
            loc("Bu IP türü sorgulanamaz.", "This IP type cannot be queried.")
        )
    return str(addr)

def ip_lookup_url(ip: str) -> str:
    return f"https://{IPWHO_HOST}/{quote(normalize_public_ip(ip), safe=':')}"

def _assert_ipwho(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != IPWHO_HOST:
        raise ToolExecutionError(
            loc(
                "IP isteği yalnızca ipwho.is üzerinde kalır.",
                "IP requests must stay on ipwho.is.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("IP adresinde kullanıcı bilgisi olamaz.", "IP URLs cannot include user info.")
        )
    return url

async def lookup_ip(ip: str) -> dict[str, Any]:
    """Genel bir IP'nin ülke/şehir/ASN özetini okur."""
    url = _assert_ipwho(ip_lookup_url(ip))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc("IP API yönlendirmesi kabul edilmez.", "IP API redirects are not accepted.")
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"IP konumu alınamadı: {exc}", f"Could not fetch IP location: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("IP yanıtı geçersiz.", "IP response is invalid."))
    if payload.get("success") is False:
        return {
            "ok": True,
            "found": False,
            "ip": normalize_public_ip(ip),
            "reason": str(payload.get("message") or loc("IP bulunamadı.", "IP not found."))[:200],
        }
    conn = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
    return {
        "ok": True,
        "found": True,
        "ip": str(payload.get("ip") or normalize_public_ip(ip))[:80],
        "country": str(payload.get("country") or "")[:80],
        "country_code": str(payload.get("country_code") or "")[:8],
        "region": str(payload.get("region") or "")[:80],
        "city": str(payload.get("city") or "")[:80],
        "org": str(conn.get("org") or payload.get("org") or "")[:160],
        "asn": conn.get("asn"),
        "source": IPWHO_HOST,
    }
