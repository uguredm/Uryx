"""Piper ses kataloğu ve indirme yardımcıları.

Sesler Hugging Face ``rhasspy/piper-voices`` deposundan indirilir ve
``PIPER_VOICE_DIR`` altında kalıcı bir volume'de saklanır.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("tts.voices")

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

@dataclass(frozen=True, slots=True)
class VoiceSpec:
    """Katalogdaki bir ses."""

    id: str
    name: str
    language: str
    quality: str

    path: str

    @property
    def onnx_url(self) -> str:
        """Model dosyasının URL'i."""
        return f"{HF_BASE}/{self.path}/{self.id}.onnx"

    @property
    def config_url(self) -> str:
        """Model yapılandırmasının URL'i."""
        return f"{HF_BASE}/{self.path}/{self.id}.onnx.json"

CATALOG: dict[str, VoiceSpec] = {
    v.id: v
    for v in [
        VoiceSpec(
            id="tr_TR-dfki-medium",
            name="DFKI (Türkçe, kadın)",
            language="tr",
            quality="medium",
            path="tr/tr_TR/dfki/medium",
        ),
        VoiceSpec(
            id="en_US-lessac-medium",
            name="Lessac (İngilizce)",
            language="en",
            quality="medium",
            path="en/en_US/lessac/medium",
        ),
    ]
}

DEFAULT_VOICE = "tr_TR-dfki-medium"

def voice_dir(root: Path) -> Path:
    """Ses klasörünü döndürür (yoksa oluşturur)."""
    root.mkdir(parents=True, exist_ok=True)
    return root

def local_paths(root: Path, voice_id: str) -> tuple[Path, Path]:
    """Bir sesin yerel ``(onnx, config)`` yollarını döndürür."""
    return root / f"{voice_id}.onnx", root / f"{voice_id}.onnx.json"

def is_installed(root: Path, voice_id: str) -> bool:
    """Ses yerelde kurulu mu?"""
    onnx, config = local_paths(root, voice_id)
    return onnx.exists() and onnx.stat().st_size > 1_000_000 and config.exists()

def installed_voices(root: Path) -> list[str]:
    """Kurulu tüm seslerin kimlikleri."""
    if not root.exists():
        return []
    return sorted(
        path.stem for path in root.glob("*.onnx") if is_installed(root, path.stem)
    )

async def download_voice(root: Path, voice_id: str, *, timeout: float = 300.0) -> bool:
    """Sesi indirir.

    Returns:
        İndirme başarılıysa ``True``.
    """
    spec = CATALOG.get(voice_id)
    if spec is None:
        logger.warning("Bilinmeyen ses: %s", voice_id)
        return False
    if is_installed(root, voice_id):
        return True

    voice_dir(root)
    onnx_path, config_path = local_paths(root, voice_id)
    logger.info("Ses indiriliyor: %s", voice_id)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for url, target in ((spec.config_url, config_path), (spec.onnx_url, onnx_path)):
                temp = target.with_suffix(target.suffix + ".part")
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with temp.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 256):
                            handle.write(chunk)
                temp.replace(target)
    except (httpx.HTTPError, OSError) as exc:
        logger.error("Ses indirilemedi (%s): %s", voice_id, exc)
        for path in (onnx_path, config_path):
            part = path.with_suffix(path.suffix + ".part")
            part.unlink(missing_ok=True)
        return False

    logger.info("Ses hazır: %s", voice_id)
    return True

async def ensure_voice(root: Path, voice_id: str) -> str | None:
    """İstenen sesi hazırlar; olmazsa kurulu bir sese düşer.

    Returns:
        Kullanılabilir ses kimliği veya ``None``.
    """
    if is_installed(root, voice_id):
        return voice_id
    if await download_voice(root, voice_id):
        return voice_id

    for candidate in CATALOG:
        if candidate == voice_id:
            continue
        if is_installed(root, candidate):
            logger.warning("%s kullanılamıyor — %s sesine düşülüyor", voice_id, candidate)
            return candidate

    for candidate in (DEFAULT_VOICE,):
        if candidate != voice_id and await download_voice(root, candidate):
            logger.warning("%s kullanılamıyor — %s sesine düşülüyor", voice_id, candidate)
            return candidate

    existing = installed_voices(root)
    return existing[0] if existing else None

def catalog_entries(root: Path) -> list[dict[str, object]]:
    """Katalog + kurulu durum bilgisini döndürür."""
    from edge import EDGE_VOICES

    entries = [
        {
            "id": spec.id,
            "name": spec.name,
            "language": spec.language,
            "quality": spec.quality,
            "installed": is_installed(root, spec.id),
        }
        for spec in CATALOG.values()
    ]
    for voice_id, meta in EDGE_VOICES.items():
        entries.insert(
            0,
            {
                "id": voice_id,
                "name": meta["name"],
                "language": meta["language"],
                "quality": meta["quality"],
                "installed": True,
            },
        )
    known = {e["id"] for e in entries}
    for voice_id in installed_voices(root):
        if voice_id not in known:
            entries.append(
                {
                    "id": voice_id,
                    "name": voice_id,
                    "language": voice_id.split("_")[0] if "_" in voice_id else "?",
                    "quality": "unknown",
                    "installed": True,
                }
            )
    return entries

def sync_download(root: Path, voice_id: str) -> bool:
    """Senkron indirme yardımcısı (script kullanımı için)."""
    return asyncio.run(download_voice(root, voice_id))
