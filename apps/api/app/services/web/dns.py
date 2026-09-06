"""Cloudflare DoH DNS kaydı — anahtarsız, sabit host, kabuk yok.

https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

DOH_HOST = "cloudflare-dns.com"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9-]{1,63})+\.?$")
_TYPES = frozenset({"A", "AAAA", "MX", "TXT", "NS", "CNAME"})

def normalize_dns_name(value: str) -> str:
    token = (value or "").strip().rstrip(".").casefold()
    if token in {"localhost", "localhost.localdomain"} or token.endswith(".local"):
        raise ToolExecutionError(loc("Yerel ad sorgulanamaz.", "Local names cannot be queried."))
    try:
        addr = ipaddress.ip_address(token)
    except ValueError:
        addr = None
    if addr is not None:
        raise ToolExecutionError(
            loc(
                "IP yerine alan adı ver. IP konumu için ip_lookup kullan.",
                "Provide a domain name, not an IP. Use ip_lookup for IP location.",
            )
        )
    if not _NAME_RE.match(token) or ".." in token or len(token) > 253:
        raise ToolExecutionError(loc("Alan adı geçersiz.", "Domain name is invalid."))
    return token

def normalize_dns_type(value: str | None) -> str:
    token = (value or "A").strip().upper()
    if token not in _TYPES:
        raise ToolExecutionError(
            loc(
                "Kayıt türü A, AAAA, MX, TXT, NS veya CNAME olmalı.",
                "Record type must be A, AAAA, MX, TXT, NS, or CNAME.",
            )
        )
    return token

def dns_lookup_url(name: str, *, record_type: str = "A") -> str:
    query = urlencode({"name": normalize_dns_name(name), "type": normalize_dns_type(record_type)})
    return f"https://{DOH_HOST}/dns-query?{query}"

def _assert_doh(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != DOH_HOST:
        raise ToolExecutionError(
            loc(
                "DNS isteği yalnızca cloudflare-dns.com üzerinde kalır.",
                "DNS requests must stay on cloudflare-dns.com.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("DNS adresinde kullanıcı bilgisi olamaz.", "DNS URLs cannot include user info.")
        )
    return url

async def lookup_dns(name: str, *, record_type: str = "A") -> dict[str, Any]:
    """A/AAAA/MX/TXT/NS/CNAME kayıtlarını DoH ile okur."""
    kind = normalize_dns_type(record_type)
    url = _assert_doh(dns_lookup_url(name, record_type=kind))
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/dns-json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc("DNS yönlendirmesi kabul edilmez.", "DNS redirects are not accepted.")
                )
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"DNS kaydı alınamadı: {exc}", f"Could not fetch DNS record: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("DNS yanıtı geçersiz.", "DNS response is invalid."))
    answers: list[str] = []
    for item in (payload.get("Answer") or [])[:16]:
        if not isinstance(item, dict):
            continue
        data = str(item.get("data") or "").strip()[:500]
        if data:
            answers.append(data)
    return {
        "ok": True,
        "name": normalize_dns_name(name),
        "type": kind,
        "status": payload.get("Status"),
        "answers": answers,
        "count": len(answers),
        "source": DOH_HOST,
    }
