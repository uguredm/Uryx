"""Salt-okunur URL okuma — MCP fetch / Continue ``@url`` kalıbı, kopya değil.

Oturum açmaz, JavaScript çalıştırmaz. Uryx Web (``browser_read_page``) bunun
yerine JS ve çerez isteyen sayfalar içindir.

SSRF: şema http/https; userinfo yok; her atlamada DNS'teki *tüm* A/AAAA
kayıtları genel olmalı (MCP servers #4205 / #4226). ``follow_redirects=True``
kullanılmaz — 302 ile 127.0.0.1'e kaçış kapanır. Bağlantı, doğrulanan IP'ye
pinlenir (validate-then-connect DNS-rebinding TOCTOU yok).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import ParseResult, urljoin, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc
from app.services.rag.parsers import html_to_text

_MAX_REDIRECTS = 5
_MAX_BYTES = 1_000_000
_DEFAULT_CHARS = 8000
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google.com",
    }
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

def assert_public_http_url(value: str) -> str:
    """URL'yi doğrular; özel/yerel/metadata hedeflerini reddeder.

    Returns:
        Normalize edilmiş URL (fragment düşer).
    """
    parsed, host = _parse_http_url(value)
    _resolve_public_ips(host)
    return parsed._replace(fragment="").geturl()

def pin_public_http_url(url: str) -> tuple[str, str, dict[str, Any]]:
    """Doğrulanmış URL'yi bağlanılacak IP'ye sabitler.

    Returns:
        (bağlantı URL'si, Host başlığı, httpx extensions)
    """
    parsed, host = _parse_http_url(url)
    addresses = _resolve_public_ips(host)
    chosen = _pick_connect_ip(addresses)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    netloc = f"[{chosen}]:{port}" if chosen.version == 6 else f"{chosen}:{port}"
    connect_url = parsed._replace(fragment="", netloc=netloc).geturl()
    default_port = 443 if parsed.scheme == "https" else 80
    host_header = host if parsed.port in {None, default_port} else f"{host}:{parsed.port}"
    extensions: dict[str, Any] = {}
    if parsed.scheme == "https":
        extensions["sni_hostname"] = host
    return connect_url, host_header, extensions

def _parse_http_url(value: str) -> tuple[ParseResult, str]:
    raw = (value or "").strip()
    if not raw:
        raise ToolExecutionError(loc("Sayfa adresi boş olamaz.", "Page URL cannot be empty."))
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ToolExecutionError(
            loc(
                "Yalnızca http ve https adresleri okunabilir.",
                "Only http and https URLs can be read.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc(
                "Adreste kullanıcı adı veya parola olamaz.",
                "URLs cannot include a username or password.",
            )
        )
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host or host in _BLOCKED_HOSTS:
        raise ToolExecutionError(
            loc(
                "Bu adres yerel veya özel ağa ait; okunamaz.",
                "This address belongs to a local or private network and cannot be read.",
            )
        )
    if host.endswith((".local", ".localhost", ".internal", ".lan")):
        raise ToolExecutionError(
            loc(
                "Bu adres yerel veya özel ağa ait; okunamaz.",
                "This address belongs to a local or private network and cannot be read.",
            )
        )
    if host == "metadata" or host.endswith(".metadata.google.internal"):
        raise ToolExecutionError(
            loc("Bulut meta veri adresi okunamaz.", "Cloud metadata addresses cannot be read.")
        )
    return parsed, host

def _resolve_public_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public_ip(literal):
            raise ToolExecutionError(
                loc("Özel veya yerel IP adresi okunamaz.", "Private or local IP addresses cannot be read.")
            )
        return [literal]
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ToolExecutionError(
            loc(f"Adres çözülemedi: {host}", f"Could not resolve address: {host}")
        ) from exc
    if not infos:
        raise ToolExecutionError(
            loc(f"Adres çözülemedi: {host}", f"Could not resolve address: {host}")
        )
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        ip_text = sockaddr[0]
        if isinstance(ip_text, bytes):
            ip_text = ip_text.decode()
        if "%" in ip_text:
            ip_text = ip_text.split("%", 1)[0]
        address = ipaddress.ip_address(ip_text)
        key = str(address)
        if key in seen:
            continue
        seen.add(key)
        if not _is_public_ip(address):
            raise ToolExecutionError(
                loc(
                    "Bu adres özel veya yerel bir IP'ye çözülüyor; okunamaz.",
                    "This address resolves to a private or local IP and cannot be read.",
                )
            )
        addresses.append(address)
    if not addresses:
        raise ToolExecutionError(
            loc(f"Adres çözülemedi: {host}", f"Could not resolve address: {host}")
        )
    return addresses

def _pick_connect_ip(
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    for address in addresses:
        if address.version == 4:
            return address
    return addresses[0]

def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        elif address.sixtofour is not None:
            address = address.sixtofour
        elif address.teredo is not None:
            address = address.teredo[1]
    if isinstance(address, ipaddress.IPv4Address) and address in _CGNAT:
        return False
    return bool(address.is_global)

async def fetch_public_page(
    url: str,
    *,
    max_chars: int = _DEFAULT_CHARS,
    start_index: int = 0,
) -> dict[str, Any]:
    """Herkese açık bir HTTP sayfasını çeker, HTML'i düz metne çevirir."""
    logical = url
    limit = max(500, min(int(max_chars), 20_000))
    offset = max(0, int(start_index))
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.1",
    }

    async with httpx.AsyncClient(follow_redirects=False, timeout=15.0, trust_env=False) as client:
        response: httpx.Response | None = None
        for _hop in range(_MAX_REDIRECTS + 1):
            connect_url, host_header, extensions = pin_public_http_url(logical)
            hop_headers = {**headers, "Host": host_header}
            try:
                response = await client.get(
                    connect_url, headers=hop_headers, extensions=extensions
                )
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    loc(f"Sayfa okunamadı: {exc}", f"Could not read page: {exc}")
                ) from exc
            if response.status_code in {301, 302, 303, 307, 308}:
                location = (response.headers.get("location") or "").strip()
                if not location:
                    raise ToolExecutionError(
                        loc("Yönlendirme adresi boş.", "Redirect URL is empty.")
                    )
                logical = urljoin(logical, location)
                continue
            break
        else:
            raise ToolExecutionError(
                loc("Çok fazla yönlendirme; sayfa okunamadı.", "Too many redirects; page could not be read.")
            )

    assert response is not None
    if response.status_code >= 400:
        raise ToolExecutionError(
            loc(
                f"Sayfa HTTP {response.status_code} döndü.",
                f"The page returned HTTP {response.status_code}.",
            )
        )
    content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
    if content_type.startswith(("image/", "audio/", "video/", "application/octet-stream")):
        raise ToolExecutionError(
            loc(
                "Bu adres ikili dosya; metin olarak okunamaz.",
                "This address is a binary file and cannot be read as text.",
            )
        )
    body = response.content[:_MAX_BYTES]
    text = body.decode(response.encoding or "utf-8", errors="replace")
    if "html" in content_type or "<html" in text[:400].casefold():
        extracted = html_to_text(text)
    else:
        extracted = text.strip()
    if not extracted:
        raise ToolExecutionError(
            loc("Sayfadan metin çıkarılamadı.", "No text could be extracted from the page.")
        )
    slice_ = extracted[offset : offset + limit]
    truncated = offset + len(slice_) < len(extracted)
    return {
        "url": logical[:2000],
        "status": response.status_code,
        "content_type": content_type or "text/html",
        "title": _first_line(extracted),
        "text": slice_,
        "truncated": truncated,
        "next_start": (offset + len(slice_)) if truncated else None,
        "chars": len(extracted),
        "javascript": False,
        "logged_in": False,
    }

def _first_line(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:200]
    return ""
