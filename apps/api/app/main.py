"""Uryx API — FastAPI uygulama giriş noktası."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.v1.routes import chat, documents, memory, speech, system, tools
from app.api.v1.routes import settings as settings_routes
from app.api.ws import chat as ws_chat
from app.api.ws import host as ws_host
from app.api.ws import speech as ws_speech
from app.api.ws import system as ws_system
from app.core.config import get_settings
from app.core.container import Container
from app.core.errors import register_exception_handlers
from app.core.locale import language_from_headers, reset_ui_language, set_ui_language
from app.core.logging import configure_logging, get_logger
from app.schemas.system import HealthResponse

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama yaşam döngüsü: bağımlılıkları kurar ve kapatır."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    logger.info(
        "starting", app=settings.app_name, version=settings.app_version, env=settings.environment
    )

    container = Container.build(settings)
    app.state.container = container
    await container.startup()

    logger.info("started", auth=settings.auth_enabled)
    try:
        yield
    finally:
        logger.info("shutting_down")
        await container.shutdown()

def create_app() -> FastAPI:
    """FastAPI uygulamasını kurar."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Yerel çalışan Türkçe masaüstü yapay zekâ asistanının backend'i. "
            "Electron uygulaması REST ve WebSocket üzerinden buraya bağlanır."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _ui_language_middleware(request: Request, call_next):
        raw = language_from_headers(request.headers)
        token = set_ui_language(raw) if raw else None
        try:
            return await call_next(request)
        finally:
            if token is not None:
                reset_ui_language(token)

    register_exception_handlers(app)

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(chat.router)
    api_v1.include_router(chat.conversations, prefix="/chat")
    api_v1.include_router(memory.router)
    api_v1.include_router(documents.router)
    api_v1.include_router(tools.router)
    api_v1.include_router(system.router)
    api_v1.include_router(speech.router)
    api_v1.include_router(settings_routes.router)
    app.include_router(api_v1)

    app.include_router(ws_chat.router)
    app.include_router(ws_system.router)
    app.include_router(ws_host.router)
    app.include_router(ws_speech.router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Konteyner healthcheck'i ve masaüstü bağlantı testi.

        Bu endpoint token gerektirmez; yalnızca servis durumlarını özetler.
        """
        container: Container = app.state.container
        statuses = await container.system.services(use_cache=True)
        service_map = {s.name: s.state for s in statuses}
        critical_down = any(service_map.get(name) == "down" for name in ("postgres", "qdrant"))
        snap = container.host_bridge.snapshot()
        bridge_state = str(snap.get("state") or "down")
        if bridge_state not in {"up", "down", "degraded"}:
            bridge_state = "up" if snap.get("connected") else "down"
        return HealthResponse(
            status="degraded" if critical_down or bridge_state == "degraded" else "ok",
            version=settings.app_version,
            services=service_map,
            host_bridge=bridge_state,  # type: ignore[arg-type]
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        """Kök endpoint."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
        }

    return app

app = create_app()
