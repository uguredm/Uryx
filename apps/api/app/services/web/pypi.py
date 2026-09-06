"""PyPI paket özeti — anahtarsız, sabit host, kabuk yok.

https://warehouse.pypa.io/api-reference/json.html
https://pypi.org/pypi/{name}/json
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.errors import ToolExecutionError
from app.core.locale import loc

PYPI_HOST = "pypi.org"
_USER_AGENT = "Uryx/1.0.0 (local-assistant; +https://github.com/uguredm/Uryx)"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

def normalize_pypi_name(value: str) -> str:
    token = (value or "").strip()
    if not _NAME_RE.match(token) or "/" in token:
        raise ToolExecutionError(
            loc(
                "PyPI paket adı harf/rakam/._- olmalı.",
                "PyPI package name must be letters, digits, or ._- characters.",
            )
        )
    return token

def pypi_url(name: str) -> str:
    return f"https://{PYPI_HOST}/pypi/{quote(normalize_pypi_name(name), safe='')}/json"

def _assert_pypi(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host != PYPI_HOST:
        raise ToolExecutionError(
            loc(
                "PyPI isteği yalnızca pypi.org üzerinde kalır.",
                "PyPI requests must stay on pypi.org.",
            )
        )
    if parsed.username or parsed.password:
        raise ToolExecutionError(
            loc("PyPI adresinde kullanıcı bilgisi olamaz.", "PyPI URLs cannot include user info.")
        )
    return url

async def lookup_pypi(name: str) -> dict[str, Any]:
    """Paket sürümü, özet ve proje adresi."""
    url = _assert_pypi(pypi_url(name))
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=12.0, follow_redirects=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ToolExecutionError(
                    loc("PyPI yönlendirmesi kabul edilmez.", "PyPI redirects are not accepted.")
                )
            if response.status_code == 404:
                return {
                    "ok": True,
                    "found": False,
                    "name": normalize_pypi_name(name),
                    "reason": loc(
                        "Paket bulunamadı. web_search dene.",
                        "Package not found. Try web_search.",
                    ),
                }
            response.raise_for_status()
            payload = response.json()
    except ToolExecutionError:
        raise
    except httpx.HTTPError as exc:
        raise ToolExecutionError(
            loc(f"PyPI kaydı alınamadı: {exc}", f"Could not fetch PyPI record: {exc}")
        ) from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(loc("PyPI yanıtı geçersiz.", "PyPI response is invalid."))
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    urls = info.get("project_urls") if isinstance(info.get("project_urls"), dict) else {}
    return {
        "ok": True,
        "found": True,
        "name": str(info.get("name") or normalize_pypi_name(name))[:80],
        "version": str(info.get("version") or "")[:40],
        "summary": str(info.get("summary") or "")[:400],
        "license": str(info.get("license") or "")[:80],
        "home_page": str(info.get("home_page") or urls.get("Homepage") or "")[:2000],
        "package_url": str(info.get("package_url") or "")[:2000],
        "requires_python": str(info.get("requires_python") or "")[:40],
        "source": PYPI_HOST,
    }
