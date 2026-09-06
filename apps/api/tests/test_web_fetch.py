"""SSRF-korumalı web_fetch ve haber aracı."""

from __future__ import annotations

import socket
from typing import ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.services.chat.orchestrator import (
    _filter_tool_schemas,
    _news_lookup_requested,
    _page_fetch_requested,
)
from app.services.tools.policy import normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.fetch import assert_public_http_url, fetch_public_page, pin_public_http_url

_PUBLIC_V4 = "93.184.216.34"

def _public_addrinfo(host: str, *_args: object, **_kwargs: object):
    if host in {"example.com", "www.example.com", "evil.example"}:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_V4, 0))]
    raise OSError("nxdomain")

class TestSsrfGate:
    def test_localhost_ve_ozel_ip_reddedilir(self) -> None:
        for url in (
            "http://127.0.0.1/",
            "http://localhost/secret",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.1/",
            "http://0.0.0.0/",
            "http://[::1]/",
            "http://[fc00::1]/",
            "http://2130706433/",
            "http://0x7f000001/",
            "file:///etc/passwd",
            "http://user:pass@example.com/",
        ):
            with pytest.raises(ToolExecutionError):
                assert_public_http_url(url)

    def test_ipv4_mapped_loopback_reddedilir(self) -> None:
        with pytest.raises(ToolExecutionError):
            assert_public_http_url("http://[::ffff:127.0.0.1]/")

    def test_hostname_ozel_ipe_cozulurse_reddedilir(self) -> None:
        def loopback(host: str, *_a: object, **_k: object):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=loopback),
            pytest.raises(ToolExecutionError, match="özel veya yerel"),
        ):
            assert_public_http_url("https://evil.example/")

    def test_baglanti_ipye_pinlenir(self) -> None:
        with patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo):
            connect_url, host_header, extensions = pin_public_http_url("https://example.com/page")
        assert connect_url.startswith(f"https://{_PUBLIC_V4}:443/")
        assert host_header == "example.com"
        assert extensions["sni_hostname"] == "example.com"

class TestFetchPage:
    async def test_html_duz_metne_doner(self) -> None:
        class Response:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {"content-type": "text/html; charset=utf-8"}
            content = (
                b"<html><body><h1>Baslik</h1><script>x</script><p>Govde metni</p></body></html>"
            )
            encoding = "utf-8"
            url = "https://example.com/page"

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(
                self,
                url: str,
                headers: dict[str, str] | None = None,
                extensions: dict[str, object] | None = None,
            ) -> Response:
                assert url.startswith(f"https://{_PUBLIC_V4}")
                assert headers is not None
                assert headers["Host"] == "example.com"
                assert extensions == {"sni_hostname": "example.com"}
                return Response()

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
        ):
            result = await fetch_public_page("https://example.com/page")

        assert result["status"] == 200
        assert result["url"].startswith("https://example.com")
        assert "Govde" in result["text"]
        assert "script" not in result["text"].casefold()
        assert result["javascript"] is False

    async def test_yonlendirme_yerel_adrese_gitmez(self) -> None:
        class Response:
            def __init__(
                self, status: int, location: str = "", url: str = "https://example.com"
            ) -> None:
                self.status_code = status
                self.headers = {"location": location} if location else {"content-type": "text/html"}
                self.content = b"ok"
                self.encoding = "utf-8"
                self.url = url

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                self.n = 0

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(
                self,
                url: str,
                headers: dict[str, str] | None = None,
                extensions: dict[str, object] | None = None,
            ) -> Response:
                self.n += 1
                if self.n == 1:
                    return Response(302, "http://127.0.0.1/secret")
                return Response(200)

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
            pytest.raises(ToolExecutionError),
        ):
            await fetch_public_page("https://example.com/go")

    async def test_dns_rebinding_ikinci_cozumu_kullanmaz(self) -> None:
        seen: list[str] = []
        calls = {"n": 0}

        def flapping(host: str, *_a: object, **_k: object):
            calls["n"] += 1
            if calls["n"] == 1:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_V4, 0))]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

        class Response:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {"content-type": "text/plain"}
            content = b"ok"
            encoding = "utf-8"
            url = f"https://{_PUBLIC_V4}/"

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(
                self,
                url: str,
                headers: dict[str, str] | None = None,
                extensions: dict[str, object] | None = None,
            ) -> Response:
                seen.append(url)
                assert "127.0.0.1" not in url
                assert url.startswith(f"https://{_PUBLIC_V4}")
                assert headers is not None
                assert headers["Host"] == "evil.example"
                return Response()

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=flapping),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
        ):
            result = await fetch_public_page("https://evil.example/")

        assert result["text"] == "ok"
        assert seen == [f"https://{_PUBLIC_V4}:443/"]
        assert calls["n"] == 1

    async def test_start_index_sayfalama(self) -> None:
        class Response:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {"content-type": "text/plain"}
            content = ("A" * 20 + "XYZ" + "B" * 600).encode()
            encoding = "utf-8"
            url = "https://example.com/page"

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(self, *_a: object, **_k: object) -> Response:
                return Response()

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
        ):
            result = await fetch_public_page(
                "https://example.com/page", max_chars=500, start_index=20
            )

        assert result["text"].startswith("XYZ")
        assert result["truncated"] is True
        assert result["next_start"] == 520

    async def test_ikili_icerik_reddedilir(self) -> None:
        class Response:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {"content-type": "image/png"}
            content = b"\x89PNG"
            encoding = "utf-8"
            url = "https://example.com/a.png"

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(self, *_a: object, **_k: object) -> Response:
                return Response()

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
            pytest.raises(ToolExecutionError, match="ikili"),
        ):
            await fetch_public_page("https://example.com/a.png")

    async def test_cok_fazla_yonlendirme(self) -> None:
        class Response:
            status_code = 302
            headers: ClassVar[dict[str, str]] = {"location": "https://example.com/next"}
            content = b""
            encoding = "utf-8"
            url = "https://example.com/go"

        class Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *_a: object) -> bool:
                return False

            async def get(self, *_a: object, **_k: object) -> Response:
                return Response()

        with (
            patch("app.services.web.fetch.socket.getaddrinfo", side_effect=_public_addrinfo),
            patch("app.services.web.fetch.httpx.AsyncClient", Client),
            pytest.raises(ToolExecutionError, match="yönlendirme"),
        ):
            await fetch_public_page("https://example.com/go")

class TestNewsAndCatalog:
    def test_alias_fetch_ve_haber(self) -> None:
        assert normalize_tool_name("fetch_url") == "web_fetch"
        assert normalize_tool_name("search_news") == "web_news"

    def test_kayit_dusuk_risk_backend(self) -> None:
        registry = ToolRegistry()
        fetch = registry.get("web_fetch")
        news = registry.get("web_news")
        assert fetch.execution.value == "backend"
        assert news.execution.value == "backend"
        assert fetch.risk.value == "low"
        cleaned = registry.validate_arguments(
            "web_fetch", {"url": "https://example.com", "extra": 1}
        )
        assert cleaned["url"].startswith("https://")
        assert "extra" not in cleaned

    def test_intent_filtre_haber_ve_link(self, container) -> None:
        schemas = container.registry.openai_schemas(categories={"web"})
        news = _filter_tool_schemas("Ankara gündem haberleri", schemas, {"web"})
        assert {item["function"]["name"] for item in news} == {"web_news", "web_research"}
        link = _filter_tool_schemas(
            "https://example.com/docs/api sayfasını oku", schemas, {"web"}
        )
        assert {item["function"]["name"] for item in link} == {"web_fetch", "web_search"}
        song = _filter_tool_schemas("Manifest'in son şarkısı ne?", schemas, {"web"})
        assert {item["function"]["name"] for item in song} == {"web_research"}

    def test_haber_ve_link_tespiti(self) -> None:
        assert _news_lookup_requested("Bugünün manşetleri neler?") is True
        assert _page_fetch_requested("Bu linki oku: https://example.com/a") is True
        assert _page_fetch_requested("Spotify'da şarkı aç") is False

    async def test_backend_haber_calisir(self, container) -> None:
        async def fake_news(
            query: str,
            *,
            max_results: int = 10,
            timelimit: str = "m",
            region: str = "wt-wt",
            safesearch: str = "moderate",
            source: str = "",
        ):
            return [
                {
                    "title": query,
                    "summary": "özet",
                    "url": "https://example.com/haber",
                    "published": "2026-08-16",
                    "source": "AA",
                }
            ][:max_results]

        container.backend_tools._web_search.news = fake_news  # type: ignore[method-assign]
        result = await container.backend_tools.execute(
            "web_news", {"query": "Ankara", "timelimit": "d"}
        )
        assert result["count"] == 1
        assert result["results"][0]["source"] == "AA"

    async def test_backend_fetch_ssrf_engeller(self, container) -> None:
        with pytest.raises(ToolExecutionError):
            await container.backend_tools.execute("web_fetch", {"url": "http://127.0.0.1/"})
