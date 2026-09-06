"""Faz 4.6 ürün E2E planı — canlı GPU/Whisper/VM default pytest'te yok."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from e2e_product import (  # noqa: E402
    JOB_IDS,
    classify_job,
    parse_nvidia_smi_vram_mib,
    silent_wav_bytes,
)

def test_uc_is_playwright_degil() -> None:
    assert JOB_IDS == ("installer", "whisper_fixture", "llm_generate")
    source = (ROOT / "scripts" / "e2e_product.py").read_text(encoding="utf-8")
    assert "playwright" not in source.lower()
    assert "page.click" not in source

def test_sessiz_wav_riff() -> None:
    payload = silent_wav_bytes(duration_ms=300)
    assert payload[:4] == b"RIFF"
    assert payload[8:12] == b"WAVE"
    assert len(payload) > 44

def test_nvidia_smi_vram() -> None:
    assert parse_nvidia_smi_vram_mib("12288") == 12288
    assert parse_nvidia_smi_vram_mib("") is None

def test_varsayilan_canli_isler_atlanir() -> None:
    assert classify_job("whisper_fixture", whisper_up=False, llm_up=False, e2e_vm=False) == "skip"
    assert classify_job("llm_generate", whisper_up=False, llm_up=False, e2e_vm=False) == "skip"
    assert classify_job("installer", whisper_up=False, llm_up=False, e2e_vm=False) == "skip"
