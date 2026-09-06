"""Ürün E2E iskeleti (Faz 4.6) — tarayıcı tıklama yok.

Üç iş: (1) VM installer, (2) Whisper fixture WAV, (3) 8B + nvidia-smi.
Canlı servis yoksa atlar (çıkış 0). Default pytest bu dosyayı import eder, HTTP atmaz.

    python scripts/e2e_product.py
    python scripts/e2e_product.py --whisper-url http://127.0.0.1:8090
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
JOB_IDS = ("installer", "whisper_fixture", "llm_generate")
Status = Literal["run", "skip"]

def silent_wav_bytes(duration_ms: int = 300, rate: int = 16000) -> bytes:
    """16 kHz mono PCM sessizlik — Whisper'a gidecek fixture clip."""
    frames = max(1, int(rate * duration_ms / 1000))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()

def parse_nvidia_smi_vram_mib(raw: str) -> int | None:
    """`nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits` ilk satır."""
    line = (raw or "").splitlines()[0].strip() if raw else ""
    if not line:
        return None
    token = line.split(",")[0].strip()
    try:
        return int(float(token))
    except ValueError:
        return None

def classify_job(
    job: str,
    *,
    whisper_up: bool,
    llm_up: bool,
    e2e_vm: bool,
) -> Status:
    """Varsayılan pytest: hepsi skip. Canlı koşu probe sonucuna göre run."""
    if job == "whisper_fixture":
        return "run" if whisper_up else "skip"
    if job == "llm_generate":
        return "run" if llm_up else "skip"
    if job == "installer":
        return "run" if e2e_vm else "skip"
    raise ValueError(job)

def _http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False

def probe_whisper(base: str) -> bool:
    return _http_ok(base.rstrip("/") + "/health")

def probe_llm(base: str) -> bool:
    root = base.rstrip("/")
    return _http_ok(root + "/health") or _http_ok(root + "/v1/models")

def read_nvidia_smi_vram_mib() -> int | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        completed = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return parse_nvidia_smi_vram_mib(completed.stdout)

def transcribe_fixture(whisper_url: str, timeout: float = 60.0) -> dict[str, object]:
    """Sessiz WAV gönderir; servis 200 dönmeli (metin boş olabilir)."""
    boundary = "uryxe2eboundary"
    wav = silent_wav_bytes()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="silence.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        whisper_url.rstrip("/") + "/transcribe",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def ping_llm_generate(llm_url: str, timeout: float = 60.0) -> dict[str, object]:
    """Tek token'lık generate — araç çalıştırmaz."""
    payload = json.dumps(
        {
            "model": "qwen3-8b",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4,
            "temperature": 0,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        llm_url.rstrip("/") + "/v1/chat/completions",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Uryx ürün E2E (tarayıcı tıklama yok)")
    parser.add_argument("--whisper-url", default=os.environ.get("WHISPER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--llm-url", default=os.environ.get("LLM_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args(argv)

    e2e_vm = os.environ.get("URYX_E2E_VM", "").strip() in {"1", "true", "yes"}
    whisper_up = probe_whisper(args.whisper_url)
    llm_up = probe_llm(args.llm_url)
    vram = read_nvidia_smi_vram_mib()

    print("Uryx E2E (tarayıcı tıklama yok)")
    print(f"  nvidia-smi VRAM MiB: {vram if vram is not None else 'yok'}")
    print(f"  whisper: {'up' if whisper_up else 'down'}  llm: {'up' if llm_up else 'down'}  vm={e2e_vm}")

    for job in JOB_IDS:
        status = classify_job(job, whisper_up=whisper_up, llm_up=llm_up, e2e_vm=e2e_vm)
        if status == "skip":
            print(f"  skip {job}")
            continue
        try:
            if job == "whisper_fixture":
                result = transcribe_fixture(args.whisper_url)
                print(f"  ok   {job} model={result.get('model')} text={result.get('text')!r}")
            elif job == "llm_generate":
                if vram is not None and vram < 8000:
                    print(f"  skip {job} (VRAM {vram} < 8000)")
                    continue
                body = ping_llm_generate(args.llm_url)
                choices = body.get("choices") or []
                print(f"  ok   {job} choices={len(choices)}")
            elif job == "installer":
                print("  ok   installer (URYX_E2E_VM — gerçek VM bu scriptte yok)")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"  fail {job}: {exc}", file=sys.stderr)
            return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
