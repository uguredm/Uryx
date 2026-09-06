"""Yerel güvenlik yardımcıları: local token doğrulama ve path-traversal koruması."""

from __future__ import annotations

import hmac
import os
from pathlib import Path, PurePath, PureWindowsPath

from fastapi import Header, Query, WebSocket

from app.core.config import Settings, get_settings
from app.core.errors import PathNotAllowedError, UnauthorizedError
from app.core.logging import get_logger

logger = get_logger(__name__)

TOKEN_HEADER = "X-Uryx-Token"
LEGACY_TOKEN_HEADER = "X-Jarvis-Token"

def verify_token_value(token: str | None, settings: Settings | None = None) -> None:
    """Verilen token'ı sabit zamanlı olarak doğrular.

    Args:
        token: İstemciden gelen token.
        settings: Ayar nesnesi (test edilebilirlik için enjekte edilebilir).

    Raises:
        UnauthorizedError: Token eksik veya hatalıysa.
    """
    settings = settings or get_settings()
    if not settings.auth_enabled:
        return
    if not token or not hmac.compare_digest(token, settings.uryx_local_token):
        raise UnauthorizedError("Geçersiz veya eksik yerel token.")

async def require_token(
    x_uryx_token: str | None = Header(default=None, alias=TOKEN_HEADER),
    x_jarvis_token: str | None = Header(default=None, alias=LEGACY_TOKEN_HEADER),
) -> None:
    """REST endpoint'leri için token bağımlılığı."""
    verify_token_value(x_uryx_token or x_jarvis_token)

async def require_ws_token(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket bağlantıları için token doğrulaması.

    Tarayıcı WebSocket API'si özel header göndermeye izin vermediğinden token
    query string üzerinden de kabul edilir.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return
    header_token = websocket.headers.get(TOKEN_HEADER.lower()) or websocket.headers.get(
        LEGACY_TOKEN_HEADER.lower()
    )
    verify_token_value(header_token or token, settings)

def _default_allowed_roots() -> list[Path]:
    """Ayarlarda kök verilmemişse kullanılacak varsayılan güvenli kökler."""
    roots: list[Path] = []
    for env_key in ("URYX_DATA_DIR", "JARVIS_DATA_DIR", "UPLOAD_DIR"):
        value = os.environ.get(env_key)
        if value:
            roots.append(Path(value))
    roots.append(Path(get_settings().upload_dir))
    return roots

def get_allowed_roots(settings: Settings | None = None) -> list[Path]:
    """Erişime izin verilen normalize edilmiş kök dizinleri döndürür."""
    settings = settings or get_settings()
    configured = settings.allowed_path_list
    raw_roots = [Path(p) for p in configured] if configured else _default_allowed_roots()

    roots: list[Path] = []
    for root in raw_roots:
        try:
            roots.append(_normalize(root))
        except OSError:  # pragma: no cover - erişilemeyen kök
            logger.warning("allowed_root_unreadable", path=str(root))
    return roots

def _normalize(path: Path) -> Path:
    """Sembolik bağlantıları çözerek mutlak yol üretir.

    ``Path.resolve(strict=False)`` var olmayan yollarda da çalışır; bu sayede
    "oluşturulacak dosya" yolları da doğrulanabilir.
    """
    return Path(os.path.normcase(str(path.expanduser().resolve(strict=False))))

def is_path_allowed(candidate: str | Path, settings: Settings | None = None) -> bool:
    """Yolun izin verilen köklerden birinin altında olup olmadığını söyler."""
    roots = get_allowed_roots(settings)
    if not roots:
        return False
    try:
        target = _normalize(Path(candidate))
    except (OSError, ValueError):
        return False

    for root in roots:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False

def ensure_path_allowed(candidate: str | Path, settings: Settings | None = None) -> Path:
    """Yolu doğrular ve normalize edilmiş hâlini döndürür.

    Raises:
        PathNotAllowedError: Yol izin verilen kökler dışındaysa.
    """
    if not is_path_allowed(candidate, settings):
        raise PathNotAllowedError(
            f"'{candidate}' izin verilen klasörlerin dışında.",
            details={"allowed_roots": [str(r) for r in get_allowed_roots(settings)]},
        )
    return _normalize(Path(candidate))

def safe_join(root: str | Path, *parts: str) -> Path:
    """``root`` altında güvenli birleştirme yapar (``..`` kaçışlarını engeller).

    Raises:
        PathNotAllowedError: Sonuç kök dizinin dışına çıkıyorsa.
    """
    root_path = _normalize(Path(root))

    for part in parts:
        pure = PurePath(part)
        windows = PureWindowsPath(part)
        if pure.is_absolute() or pure.drive or windows.is_absolute() or windows.drive:
            raise PathNotAllowedError("Mutlak yol parçası kabul edilmiyor.")
    candidate = _normalize(root_path.joinpath(*parts))
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise PathNotAllowedError("Yol kök dizinin dışına çıkıyor.") from exc
    return candidate
