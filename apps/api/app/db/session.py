"""Asenkron veritabanı oturum yönetimi.

PostgreSQL erişilemezse uygulama çökmez; ``Database.available`` ``False`` olur ve
sohbet bellek içi modda sürer (bkz. ARCHITECTURE.md — Fallback Matrisi).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class Database:
    """Motor + oturum fabrikası sarmalayıcısı."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self.available: bool = False
        self.last_error: str | None = None

    async def connect(self) -> None:
        """Motoru oluşturur ve bağlantıyı doğrular."""
        kwargs: dict[str, object] = {"echo": self._settings.db_echo, "pool_pre_ping": True}
        if not self._settings.database_url.startswith("sqlite"):
            kwargs |= {
                "pool_size": self._settings.db_pool_size,
                "max_overflow": self._settings.db_max_overflow,
                "pool_recycle": 1800,
            }

        self._engine = create_async_engine(self._settings.database_url, **kwargs)  # type: ignore[arg-type]
        self._sessionmaker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        await self.ping()

    async def ping(self) -> bool:
        """Bağlantıyı test eder ve ``available`` bayrağını günceller."""
        if self._engine is None:
            self.available = False
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self.available = True
            self.last_error = None
        except Exception as exc:
            self.available = False
            self.last_error = str(exc)
            logger.warning("database_unavailable", error=str(exc))
        return self.available

    async def disconnect(self) -> None:
        """Motoru kapatır."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            self.available = False

    @property
    def engine(self) -> AsyncEngine:
        """Aktif motor."""
        if self._engine is None:
            raise RuntimeError("Veritabanı motoru başlatılmadı.")
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """İşlem sınırlı bir oturum bağlamı üretir."""
        if self._sessionmaker is None:
            raise RuntimeError("Veritabanı oturum fabrikası başlatılmadı.")
        session = self._sessionmaker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_all(self) -> None:
        """Tabloları oluşturur (yalnızca test/geliştirme; üretimde Alembic)."""
        from app.db.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
