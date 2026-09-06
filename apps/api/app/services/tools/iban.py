"""Yerel IBAN doğrulama — ağ, kabuk ve eval yok.

ISO 13616: harfleri 10–35'e çevir, ilk 4 karakteri sona al, MOD-97 == 1.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.errors import ToolExecutionError
from app.core.locale import loc

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_MAX_LEN = 34
_MIN_LEN = 15

_COUNTRY_LEN: dict[str, int] = {
    "TR": 26,
    "DE": 22,
    "GB": 22,
    "FR": 27,
    "NL": 18,
    "IT": 27,
    "ES": 24,
    "AT": 20,
    "BE": 16,
    "CH": 21,
    "PL": 28,
    "SE": 24,
    "NO": 15,
    "DK": 18,
    "FI": 18,
    "IE": 22,
    "PT": 25,
    "GR": 27,
    "CZ": 24,
    "HU": 28,
    "RO": 24,
    "BG": 22,
    "HR": 21,
    "AE": 23,
    "SA": 24,
}

def normalize_iban(value: str) -> str:
    token = re.sub(r"[\s\-]+", "", (value or "")).upper()
    if not token:
        raise ToolExecutionError(loc("IBAN boş olamaz.", "IBAN cannot be empty."))
    if not _IBAN_RE.fullmatch(token) or not (_MIN_LEN <= len(token) <= _MAX_LEN):
        raise ToolExecutionError(
            loc(
                "IBAN 15–34 karakter olmalı (ülke + kontrol + hesap).",
                "IBAN must be 15–34 characters (country + check + account).",
            )
        )
    return token

def iban_mod97_ok(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    return int(digits) % 97 == 1

def format_iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))

def check_iban(value: str) -> dict[str, Any]:
    """IBAN checksum + bilinen ülke uzunluğu. Ağ yok."""
    iban = normalize_iban(value)
    country = iban[:2]
    expected = _COUNTRY_LEN.get(country)
    length_ok = expected is None or len(iban) == expected
    checksum_ok = iban_mod97_ok(iban)
    valid = bool(length_ok and checksum_ok)
    reason = ""
    if not length_ok:
        reason = f"{country} IBAN {expected} karakter olmalı."
    elif not checksum_ok:
        reason = "IBAN kontrol hanesi geçersiz."
    return {
        "ok": True,
        "valid": valid,
        "iban": iban,
        "formatted": format_iban(iban),
        "country": country,
        "reason": reason,
    }

def run_iban_check(args: dict[str, Any]) -> dict[str, Any]:
    return check_iban(str(args.get("iban") or ""))
