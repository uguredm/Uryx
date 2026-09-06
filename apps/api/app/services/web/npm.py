"""npm registry paket özeti — anahtarsız, sabit host, kabuk yok.

https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

NPM_HOST = "registry.npmjs.org"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_NAME_RE = re.compile(r"^(@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]{1,80}$")

def normalize_npm_name(value: str) -> str:
    token = (value or "").strip()
    if not _NAME_RE.match(token) or ".." in token:
        raise ToolExecutionError(loc("npm paket adı geçersiz.", "npm package name is invalid."))
    return token

def npm_url(name: str) -> str:
    clean = normalize_npm_name(name)
    return f"https://{NPM_HOST}/{quote(clean, safe='@/')}"

def _assert_npm(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != NPM_HOST:
        raise ToolExecutionError(
            loc(
                "npm isteği yalnızca registry.npmjs.org üzerinde kalır.",
                "npm requests must stay on registry.npmjs.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("npm adresinde kullanıcı bilgisi olamaz.", "npm URLs cannot include user info.")
        )
    return url

async def lookup_npm(name: str) -> dict[str, Any]:
    """Paket sürümü ve özeti; indirme yok."""
    url = _assert_npm(npm_url(name))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc("npm yönlendirmesi kabul edilmez.", "npm redirects are not accepted.")
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "name": normalize_npm_name(name),
                    "reason": loc(
                        "Paket bulunamadı. pypi_lookup veya web_search dene.",
                        "Package not found. Try pypi_lookup or web_search.",
                    ),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"npm kaydı alınamadı: {exc}", f"Could not fetch npm record: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("npm yanıtı geçersiz.", "npm response is invalid."))
    dist = payload.get("dist-tags") if isinstance(payload.get("dist-tags"), dict) else {}
    latest = str(dist.get("latest") or "")[:40]
    versions = payload.get("versions") if isinstance(payload.get("versions"), dict) else {}
    info = versions.get(latest) if latest and isinstance(versions.get(latest), dict) else {}
    return {
        "ok": True,
        "found": True,
        "name": str(payload.get("name") or normalize_npm_name(name))[:120],
        "version": latest,
        "description": str(payload.get("description") or info.get("description") or "")[:400],
        "license": str(info.get("license") or payload.get("license") or "")[:80],
        "homepage": str(payload.get("homepage") or "")[:2000],
        "source": NPM_HOST,
    }
