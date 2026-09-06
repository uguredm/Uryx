"""Lookup araçları — ekstra SSRF / özel ağ / userinfo kapıları.

Mevcut servis dosyalarını rewrite etmez; public normalize + _assert kapılarını
http / yabancı host / userinfo / loopback ile dener.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.errors import ToolExecutionError
from app.services.web import (
    air_quality,
    countries,
    dictionary,
    dns,
    doi,
    earthquakes,
    elevation,
    food,
    fx,
    holidays,
    ipgeo,
    iss,
    npm,
    pollen,
    postal,
    prayer,
    pypi,
    search,
    space_weather,
    sun,
    weather,
    wiki,
)

def _assert_rejects(fn: Callable[[str], str], url: str) -> None:
    with pytest.raises(ToolExecutionError):
        fn(url)

@pytest.mark.parametrize(
    ("assert_fn", "good"),
    [
        (ipgeo._assert_ipwho, "https://ipwho.is/8.8.8.8"),
        (dns._assert_doh, "https://cloudflare-dns.com/dns-query?name=example.com&type=A"),
        (food._assert_food, "https://world.openfoodfacts.org/api/v2/product/3017620422003.json"),
        (npm._assert_npm, "https://registry.npmjs.org/react"),
        (pypi._assert_pypi, "https://pypi.org/pypi/httpx/json"),
        (doi._assert_crossref, "https://api.crossref.org/works/10.1000/xyz"),
        (fx._assert_frankfurter, "https://api.frankfurter.dev/v2/rate/USD/TRY"),
        (iss._assert_iss, "https://api.wheretheiss.at/v1/satellites/25544"),
        (space_weather._assert_swpc, "https://services.swpc.noaa.gov/products/noaa-scales.json"),
        (holidays._assert_nager, "https://date.nager.at/api/v3/PublicHolidays/2026/TR"),
        (countries._assert_restcountries, "https://restcountries.com/v3.1/name/turkey"),
        (earthquakes._assert_usgs, "https://earthquake.usgs.gov/fdsnws/event/1/query"),
        (postal._assert_zippo, "https://api.zippopotam.us/tr/34000"),
        (prayer._assert_aladhan, "https://api.aladhan.com/v1/timingsByCity"),
        (wiki._assert_wikipedia_url, "https://tr.wikipedia.org/api/rest_v1/page/summary/Istanbul"),
        (
            dictionary._assert_wiktionary_url,
            "https://tr.wiktionary.org/api/rest_v1/page/definition/merhaba",
        ),
        (lambda u: weather._assert_host(u, weather.GEO_HOST), "https://geocoding-api.open-meteo.com/v1/search"),
        (lambda u: weather._assert_host(u, weather.WX_HOST), "https://api.open-meteo.com/v1/forecast"),
        (lambda u: air_quality._assert_host(u, air_quality.AQ_HOST), "https://air-quality-api.open-meteo.com/v1/air-quality"),
        (lambda u: pollen._assert_host(u, pollen.POLLEN_HOST), "https://air-quality-api.open-meteo.com/v1/air-quality"),
        (lambda u: sun._assert_host(u, weather.WX_HOST), "https://api.open-meteo.com/v1/forecast"),
        (lambda u: elevation._assert_host(u, weather.WX_HOST), "https://api.open-meteo.com/v1/elevation"),
    ],
)
def test_assert_http_userinfo_ve_yabanci_host(
    assert_fn: Callable[[str], str], good: str
) -> None:
    assert assert_fn(good) == good
    host = good.split("://", 1)[1].split("/", 1)[0]
    path = "/" + good.split("/", 3)[-1] if good.count("/") >= 3 else "/"
    _assert_rejects(assert_fn, good.replace("https://", "http://", 1))
    _assert_rejects(assert_fn, f"https://evil.example{path}")
    _assert_rejects(assert_fn, f"https://user:pass@{host}{path}")
    _assert_rejects(assert_fn, f"https://127.0.0.1{path}")
    _assert_rejects(assert_fn, f"https://[::1]{path}")
    _assert_rejects(assert_fn, f"https://user@{host}{path}")
    _assert_rejects(assert_fn, f"file://{host}{path}")

def test_ip_lookup_ozel_ve_ayrik_adresler() -> None:
    for token in (
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.1.1",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "2130706433",
    ):
        with pytest.raises(ToolExecutionError):
            ipgeo.normalize_public_ip(token)
    assert ipgeo.normalize_public_ip("8.8.8.8") == "8.8.8.8"

def test_dns_localhost_local_ve_ham_ip() -> None:
    for name in ("localhost", "localhost.localdomain", "printer.local", "8.8.8.8", "127.0.0.1"):
        with pytest.raises(ToolExecutionError):
            dns.normalize_dns_name(name)
    assert dns.normalize_dns_name("Example.COM.") == "example.com"

def test_barkod_ve_site_ozel_adres() -> None:
    for code in ("abc", "123", "1234567", "123456789012345", "12 34"):
        with pytest.raises(ToolExecutionError):
            food.normalize_barcode(code)
    assert food.normalize_barcode("3017620422003") == "3017620422003"
    for site in ("127.0.0.1", "10.0.0.1", "localhost", "foo.local", "[::1]"):
        with pytest.raises(ToolExecutionError):
            search.normalize_search_site(site)
