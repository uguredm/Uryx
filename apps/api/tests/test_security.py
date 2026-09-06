"""Güvenlik testleri: path traversal ve token doğrulama."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import PathNotAllowedError, UnauthorizedError
from app.core.security import (
    ensure_path_allowed,
    is_path_allowed,
    safe_join,
    verify_token_value,
)

@pytest.fixture
def sandbox(tmp_path: Path) -> Settings:
    """İzin verilen tek kökü geçici klasör olan ayarlar."""
    root = tmp_path / "izinli"
    root.mkdir()
    (root / "belge.txt").write_text("içerik", encoding="utf-8")

    gizli = tmp_path / "gizli"
    gizli.mkdir()
    (gizli / "sifreler.txt").write_text("gizli", encoding="utf-8")

    return Settings(uryx_allowed_paths=str(root), database_url="sqlite+aiosqlite:///:memory:")

class TestPathGuard:
    """Path traversal koruması."""

    def test_izinli_yol_kabul_edilir(self, sandbox: Settings, tmp_path: Path) -> None:
        assert is_path_allowed(tmp_path / "izinli" / "belge.txt", sandbox)

    def test_izinsiz_yol_reddedilir(self, sandbox: Settings, tmp_path: Path) -> None:
        assert not is_path_allowed(tmp_path / "gizli" / "sifreler.txt", sandbox)

    def test_ust_dizine_cikis_reddedilir(self, sandbox: Settings, tmp_path: Path) -> None:
        traversal = tmp_path / "izinli" / ".." / "gizli" / "sifreler.txt"
        assert not is_path_allowed(traversal, sandbox)

    def test_derin_traversal_reddedilir(self, sandbox: Settings, tmp_path: Path) -> None:
        traversal = tmp_path / "izinli" / ".." / ".." / ".." / "Windows" / "System32"
        assert not is_path_allowed(traversal, sandbox)

    def test_ensure_hata_firlatir(self, sandbox: Settings, tmp_path: Path) -> None:
        with pytest.raises(PathNotAllowedError):
            ensure_path_allowed(tmp_path / "gizli" / "sifreler.txt", sandbox)

    def test_olusturulacak_dosya_yolu_dogrulanabilir(
        self, sandbox: Settings, tmp_path: Path
    ) -> None:

        assert is_path_allowed(tmp_path / "izinli" / "yeni" / "dosya.txt", sandbox)

    def test_kok_tanimli_degilse_hicbir_yol_kabul_edilmez(self, tmp_path: Path) -> None:
        settings = Settings(
            uryx_allowed_paths="",
            upload_dir=str(tmp_path / "yok-boyle-bir-yer"),
            database_url="sqlite+aiosqlite:///:memory:",
        )
        assert not is_path_allowed("C:/Windows/System32/config", settings)

class TestSafeJoin:
    """Güvenli yol birleştirme."""

    def test_normal_birlestirme(self, tmp_path: Path) -> None:
        result = safe_join(tmp_path, "alt", "dosya.txt")
        assert str(result).endswith("dosya.txt")

    def test_traversal_engellenir(self, tmp_path: Path) -> None:
        with pytest.raises(PathNotAllowedError):
            safe_join(tmp_path, "..", "disari.txt")

    def test_mutlak_yol_reddedilir(self, tmp_path: Path) -> None:
        with pytest.raises(PathNotAllowedError):
            safe_join(tmp_path, "C:\\Windows\\System32")

class TestToken:
    """Yerel token doğrulaması."""

    def test_auth_kapaliyken_her_sey_gecer(self) -> None:
        settings = Settings(uryx_local_token="", database_url="sqlite+aiosqlite:///:memory:")
        verify_token_value(None, settings)
        verify_token_value("rastgele", settings)

    def test_dogru_token_gecer(self) -> None:
        settings = Settings(
            uryx_local_token="gizli-token", database_url="sqlite+aiosqlite:///:memory:"
        )
        verify_token_value("gizli-token", settings)

    def test_yanlis_token_reddedilir(self) -> None:
        settings = Settings(
            uryx_local_token="gizli-token", database_url="sqlite+aiosqlite:///:memory:"
        )
        with pytest.raises(UnauthorizedError):
            verify_token_value("yanlis", settings)

    def test_eksik_token_reddedilir(self) -> None:
        settings = Settings(
            uryx_local_token="gizli-token", database_url="sqlite+aiosqlite:///:memory:"
        )
        with pytest.raises(UnauthorizedError):
            verify_token_value(None, settings)
