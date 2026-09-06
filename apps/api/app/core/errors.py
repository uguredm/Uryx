"""Merkezi hata yönetimi.

Tüm uygulama hataları ``UryxError`` türevidir ve tek bir handler tarafından
tutarlı bir JSON gövdesine dönüştürülür.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.locale import loc
from app.core.logging import get_logger

logger = get_logger(__name__)

class UryxError(Exception):
    """Uygulama hatalarının kök sınıfı."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    user_message: str = "Beklenmeyen bir hata oluştu."
    message_en: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.user_message = (
            message
            if message is not None
            else loc(type(self).user_message, type(self).message_en)
        )
        self.details = details or {}
        if code:
            self.code = code
        super().__init__(self.user_message)

    def to_payload(self) -> dict[str, Any]:
        """API cevabı için sözlük gösterimi."""
        return {
            "error": {
                "code": self.code,
                "message": self.user_message,
                "details": self.details,
            }
        }

class NotFoundError(UryxError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    user_message = "Kayıt bulunamadı."
    message_en = "Record not found."

class ValidationError(UryxError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    user_message = "Geçersiz istek."
    message_en = "Invalid request."

class UnauthorizedError(UryxError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    user_message = "Yetkisiz istek."
    message_en = "Unauthorized request."

class ForbiddenError(UryxError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    user_message = "Bu işleme izin verilmiyor."
    message_en = "This action is not allowed."

class PathNotAllowedError(ForbiddenError):
    code = "path_not_allowed"
    user_message = "Bu dosya yoluna erişim izni yok."
    message_en = "Access to this file path is not allowed."

class ToolNotAllowedError(ForbiddenError):
    code = "tool_not_allowed"
    user_message = "Bu araç izin listesinde değil."
    message_en = "This tool is not on the allowlist."

class ToolBlockedError(ForbiddenError):
    code = "tool_blocked"
    user_message = "Bu araç çağrısı güvenlik politikası tarafından reddedildi."
    message_en = "This tool call was blocked by the security policy."

class ToolConfirmationRequiredError(UryxError):
    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    code = "confirmation_required"
    user_message = "Bu işlem kullanıcı onayı gerektiriyor."
    message_en = "This action requires your confirmation."

class ToolExecutionError(UryxError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "tool_execution_failed"
    user_message = "Araç çalıştırılamadı."
    message_en = "Tool failed."

class ServiceUnavailableError(UryxError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    user_message = "Servis şu anda kullanılamıyor."
    message_en = "The service is currently unavailable."

class LLMUnavailableError(ServiceUnavailableError):
    code = "llm_unavailable"
    user_message = (
        "Yerel LLM servisine ulaşılamıyor. GGUF indirildi mi ve "
        "`docker compose ps` içinde llm ayakta mı kontrol edin."
    )
    message_en = (
        "The local LLM service is unreachable. Check that the GGUF is downloaded "
        "and that llm is up in `docker compose ps`."
    )

class VectorStoreUnavailableError(ServiceUnavailableError):
    code = "vectorstore_unavailable"
    user_message = "Qdrant servisine ulaşılamıyor. RAG özellikleri devre dışı."
    message_en = "The Qdrant service is unreachable. RAG features are disabled."

class DatabaseUnavailableError(ServiceUnavailableError):
    code = "database_unavailable"
    user_message = "PostgreSQL servisine ulaşılamıyor. Geçmiş kaydedilemiyor."
    message_en = "PostgreSQL is unreachable. History cannot be saved."

class STTUnavailableError(ServiceUnavailableError):
    code = "stt_unavailable"
    user_message = "Konuşma tanıma servisi (Whisper) çalışmıyor."
    message_en = "The speech recognition service (Whisper) is down."

class TTSUnavailableError(ServiceUnavailableError):
    code = "tts_unavailable"
    user_message = "Seslendirme servisi (Piper) çalışmıyor."
    message_en = "The speech service (Piper) is down."

class HostBridgeUnavailableError(ServiceUnavailableError):
    code = "host_bridge_unavailable"
    user_message = (
        "Masaüstü uygulaması bağlı değil. Bu araç Windows tarafında çalıştığı için "
        "Uryx masaüstü uygulamasının açık olması gerekir."
    )
    message_en = (
        "The desktop app is not connected. This tool runs on Windows, so the "
        "Uryx desktop app must be open."
    )

def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI uygulamasına merkezi hata işleyicilerini bağlar."""

    @app.exception_handler(UryxError)
    async def _uryx_error_handler(_request: Request, exc: UryxError) -> JSONResponse:
        log = logger.warning if exc.status_code < 500 else logger.error
        log("uryx_error", code=exc.code, message=exc.user_message, details=exc.details)
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": loc(
                        "İstek gövdesi doğrulanamadı.",
                        "The request body could not be validated.",
                    ),
                    "details": {"errors": _safe_errors(exc)},
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Ham veritabanı hatalarını anlaşılır bir mesaja çevirir."""
        detail = str(exc)
        if "no such table" in detail or "does not exist" in detail:
            message = loc(
                "Veritabanı şeması eksik. Migration'lar uygulanmamış olabilir: "
                "`docker compose exec uryx-api alembic upgrade head`",
                "Database schema is missing. Migrations may not have been applied: "
                "`docker compose exec uryx-api alembic upgrade head`",
            )
            code = "database_schema_missing"
        else:
            message = loc(
                DatabaseUnavailableError.user_message,
                DatabaseUnavailableError.message_en,
            )
            code = DatabaseUnavailableError.code

        logger.error("database_error", code=code, error=detail[:500])
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": code, "message": message, "details": {}}},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"http_{exc.status_code}",
                    "message": str(exc.detail),
                    "details": {},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": loc(
                        "Sunucuda beklenmeyen bir hata oluştu.",
                        "An unexpected error occurred on the server.",
                    ),
                    "details": {},
                }
            },
        )

def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Doğrulama hatalarını JSON'a güvenli biçime çevirir."""
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        out.append(
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return out
