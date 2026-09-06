"""Araç çalıştırıcı.

Sorumlulukları:

1. Allowlist doğrulaması (``ToolRegistry``).
2. Argüman doğrulama/normalizasyon.
3. Risk seviyesine göre kullanıcı onayı zorunluluğu — onay backend'de karara
   bağlanır, renderer'ın gönderdiği ``confirmed`` bayrağına körü körüne güvenilmez.
4. ``host`` / ``backend`` yönlendirmesi.
5. Geçici host kopuşlarında sınırlı yeniden deneme (idempotent araçlar).
6. Süre ölçümü ve veritabanına denetim kaydı.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import Settings
from app.core.errors import (
    HostBridgeUnavailableError,
    UryxError,
    ToolBlockedError,
    ToolConfirmationRequiredError,
    ToolExecutionError,
)
from app.core.locale import loc
from app.core.logging import get_logger
from app.db.models import ToolCallStatus
from app.db.repositories.conversation import ToolCallRepository
from app.db.session import Database
from app.schemas.tools import ExecutionTarget, ToolDefinition, ToolPrepareResponse, ToolResult
from app.services.tools.backend_tools import BackendToolset
from app.services.tools.host_bridge import HostBridge
from app.services.tools.policy import (
    MAX_TRANSIENT_RETRIES,
    ConfirmationTicketStore,
    PolicyVerdict,
    SessionGrantStore,
    confirmation_satisfied,
    evaluate_call,
    is_transient_host_error,
    retry_backoff_seconds,
    retry_exhausted_message,
    should_retry_transient,
)
from app.services.tools.registry import ToolRegistry

logger = get_logger(__name__)

class ToolExecutor:
    """Araç çağrılarını güvenli biçimde yürütür."""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        host_bridge: HostBridge,
        backend_tools: BackendToolset,
        database: Database,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._host = host_bridge
        self._backend = backend_tools
        self._db = database
        self.grants = SessionGrantStore()
        self.tickets = ConfirmationTicketStore()

    def inspect(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        confirmation_enabled: bool | None = None,
        conversation_id: str | None = None,
    ) -> tuple[ToolDefinition, dict[str, Any], bool]:
        """Aracı doğrular ve onay gerekip gerekmediğini söyler.

        Returns:
            ``(tanım, temizlenmiş argümanlar, onay_gerekli)``
        """
        verdict = self.evaluate(
            tool_name,
            arguments,
            confirmation_enabled=confirmation_enabled,
            conversation_id=conversation_id,
        )
        definition = self._registry.get(tool_name)
        cleaned = self._registry.validate_arguments(tool_name, arguments)
        return definition, cleaned, verdict.needs_confirmation

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        confirmation_enabled: bool | None = None,
        conversation_id: str | None = None,
    ) -> PolicyVerdict:
        """Politika kararını (parmak izi, yükseltme, blok) üretir."""
        definition = self._registry.get(tool_name)
        cleaned = self._registry.validate_arguments(tool_name, arguments)
        enabled = (
            self._settings.require_tool_confirmation
            if confirmation_enabled is None
            else confirmation_enabled
        )
        return evaluate_call(
            definition,
            cleaned,
            confirmation_enabled=enabled,
            session_granted=self.grants.allows(conversation_id, tool_name),
        )

    def prepare(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        confirmation_enabled: bool | None = None,
        conversation_id: str | None = None,
    ) -> ToolPrepareResponse:
        """REST önizlemesi: etkili risk, blok ve varsa onay bileti."""
        definition = self._registry.get(tool_name)
        cleaned = self._registry.validate_arguments(tool_name, arguments)
        verdict = self.evaluate(
            tool_name,
            cleaned,
            confirmation_enabled=confirmation_enabled,
            conversation_id=conversation_id,
        )
        ticket: str | None = None
        if verdict.needs_confirmation and not verdict.block_reason:
            ticket = self.tickets.issue(tool_name, verdict.fingerprint)
        return ToolPrepareResponse(
            tool_name=tool_name,
            display_name=definition.display_name,
            arguments=cleaned,
            fingerprint=verdict.fingerprint,
            risk_level=definition.risk.value,
            effective_risk=verdict.effective_risk.value,
            needs_confirmation=verdict.needs_confirmation,
            remember_allowed=verdict.remember_allowed,
            confirmation_ticket=ticket,
            blocked=bool(verdict.block_reason),
            block_reason=verdict.block_reason,
        )

    def issue_ticket(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """REST onay bileti üretir (argüman parmak izine bağlı)."""
        definition = self._registry.get(tool_name)
        cleaned = self._registry.validate_arguments(tool_name, arguments)
        verdict = evaluate_call(definition, cleaned, confirmation_enabled=True)
        return self.tickets.issue(tool_name, verdict.fingerprint)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        conversation_id: str | None = None,
        confirmed: bool = False,
        confirmation_ticket: str | None = None,
        confirmation_enabled: bool | None = None,
        expected_fingerprint: str | None = None,
    ) -> ToolResult:
        """Aracı çalıştırır.

        Args:
            tool_name: Allowlist'teki araç adı.
            arguments: Ham argümanlar.
            conversation_id: Denetim kaydı için sohbet kimliği.
            confirmed: Kullanıcı onayı alınmış mı.
            confirmation_ticket: REST HIGH çağrıları için hazırlık bileti.
            confirmation_enabled: Tur bazlı onay ayarı; ``None`` ise global ayar.
            expected_fingerprint: Onay anındaki argüman parmak izi (TOCTOU).

        Raises:
            ToolConfirmationRequiredError: Onay gerekiyor ama alınmamışsa.
            ToolBlockedError: Politika çağrıyı fail-closed reddettiyse.
        """
        started = time.perf_counter()
        definition = self._registry.get(tool_name)
        cleaned = self._registry.validate_arguments(tool_name, arguments)
        enabled = (
            self._settings.require_tool_confirmation
            if confirmation_enabled is None
            else confirmation_enabled
        )
        verdict = evaluate_call(
            definition,
            cleaned,
            confirmation_enabled=enabled,
            session_granted=self.grants.allows(conversation_id, tool_name),
        )
        if verdict.block_reason:
            raise ToolBlockedError(verdict.block_reason, details={"tool_name": tool_name})

        ticket_ok = bool(
            confirmation_ticket
            and self.tickets.consume(confirmation_ticket, tool_name, verdict.fingerprint)
        )
        if not confirmation_satisfied(
            verdict,
            confirmed=confirmed,
            ticket_ok=ticket_ok,
            expected_fingerprint=expected_fingerprint,
        ):
            raise ToolConfirmationRequiredError(
                loc(
                    f"'{definition.display_name}' işlemi kullanıcı onayı gerektiriyor.",
                    f"'{definition.display_name}' requires your confirmation.",
                ),
                details={
                    "tool_name": tool_name,
                    "display_name": definition.display_name,
                    "risk_level": verdict.effective_risk.value,
                    "impact": definition.impact,
                    "arguments": cleaned,
                    "fingerprint": verdict.fingerprint,
                    "remember_allowed": verdict.remember_allowed,
                },
            )

        call_id = await self._record_start(
            tool_name, cleaned, conversation_id, definition, verdict.needs_confirmation
        )

        try:
            result = await self._dispatch(definition, cleaned)
        except UryxError as exc:
            duration = int((time.perf_counter() - started) * 1000)
            await self._record_finish(
                call_id, ToolCallStatus.FAILED, error=exc.user_message, duration_ms=duration
            )
            logger.warning(
                "tool_failed", tool=tool_name, error=exc.user_message, duration_ms=duration
            )
            return ToolResult(
                call_id=call_id or "",
                tool_name=tool_name,
                success=False,
                error=exc.user_message,
                duration_ms=duration,
                retries=int(exc.details.get("retries") or 0),
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            await self._record_finish(
                call_id, ToolCallStatus.FAILED, error=str(exc), duration_ms=duration
            )
            logger.exception("tool_unexpected_error", tool=tool_name)
            return ToolResult(
                call_id=call_id or "",
                tool_name=tool_name,
                success=False,
                error=loc(f"Beklenmeyen hata: {exc}", f"Unexpected error: {exc}"),
                duration_ms=duration,
            )

        duration = int((time.perf_counter() - started) * 1000)
        await self._record_finish(
            call_id,
            ToolCallStatus.SUCCESS,
            result=result,
            duration_ms=duration,
            approved=True if verdict.needs_confirmation else None,
        )
        logger.info("tool_succeeded", tool=tool_name, duration_ms=duration)
        return ToolResult(
            call_id=call_id or "",
            tool_name=tool_name,
            success=True,
            result=result,
            duration_ms=duration,
        )

    async def _dispatch(
        self, definition: ToolDefinition, cleaned: dict[str, Any]
    ) -> dict[str, Any]:
        """Host/backend yönlendirmesi + geçici hata yeniden denemesi."""
        if definition.execution is ExecutionTarget.HOST:
            return await self._call_host(definition.name, cleaned)
        return await self._backend.execute(definition.name, cleaned)

    async def _call_host(self, tool_name: str, cleaned: dict[str, Any]) -> dict[str, Any]:
        """Host RPC; kopuş ve gönderim hatalarında sınırlı retry."""
        last_error: HostBridgeUnavailableError | None = None
        for attempt in range(MAX_TRANSIENT_RETRIES):
            try:
                payload = await self._host.call(
                    tool_name, cleaned, timeout_seconds=self._settings.host_tool_timeout
                )
            except HostBridgeUnavailableError as exc:
                last_error = exc
                timed_out = str(exc.details.get("reason") or "") == "timeout"
                retryable = bool(exc.details.get("retryable", True))
                if should_retry_transient(
                    tool_name=tool_name,
                    attempt=attempt,
                    retryable=retryable,
                    timed_out=timed_out,
                ):
                    delay = retry_backoff_seconds(attempt)
                    logger.info(
                        "host_tool_retry",
                        tool=tool_name,
                        attempt=attempt + 1,
                        delay_s=delay,
                        reason=exc.details.get("reason"),
                    )
                    await asyncio.sleep(delay)
                    continue
                if attempt == 0:
                    raise
                raise HostBridgeUnavailableError(
                    retry_exhausted_message(exc.user_message, attempt + 1),
                    details={**exc.details, "retries": attempt + 1},
                ) from exc
            if not payload.get("success"):
                error = str(
                    payload.get("error")
                    or loc("Host aracı hata döndürdü.", "The host tool returned an error.")
                )
                if is_transient_host_error(error) and should_retry_transient(
                    tool_name=tool_name,
                    attempt=attempt,
                    retryable=True,
                    timed_out=False,
                ):
                    delay = retry_backoff_seconds(attempt)
                    logger.info(
                        "host_tool_busy_retry",
                        tool=tool_name,
                        attempt=attempt + 1,
                        delay_s=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ToolExecutionError(error, details={"tool_name": tool_name})
            return dict(payload.get("result") or {})
        assert last_error is not None
        raise HostBridgeUnavailableError(
            retry_exhausted_message(last_error.user_message, MAX_TRANSIENT_RETRIES),
            details={**last_error.details, "retries": MAX_TRANSIENT_RETRIES},
        ) from last_error

    async def record_rejection(
        self, tool_name: str, arguments: dict[str, Any], conversation_id: str | None
    ) -> None:
        """Kullanıcının reddettiği araç çağrısını kaydeder."""
        call_id = await self._record_start(
            tool_name,
            arguments,
            conversation_id,
            self._registry.get(tool_name),
            True,
        )
        await self._record_finish(
            call_id,
            ToolCallStatus.REJECTED,
            error=loc("Kullanıcı onayı reddedildi.", "User confirmation was rejected."),
            approved=False,
        )

    async def _record_start(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        conversation_id: str | None,
        definition: ToolDefinition,
        needs_confirmation: bool,
    ) -> str | None:
        """Denetim kaydını açar."""
        if not self._db.available:
            return None
        try:
            async with self._db.session() as session:
                call = await ToolCallRepository(session).create(
                    tool_name=tool_name,
                    arguments=arguments,
                    conversation_id=conversation_id,
                    risk_level=definition.risk.value,
                    required_confirmation=needs_confirmation,
                )
                return call.id
        except Exception as exc:
            logger.warning("tool_audit_start_failed", error=str(exc))
            return None

    async def _record_finish(
        self,
        call_id: str | None,
        status: ToolCallStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int = 0,
        approved: bool | None = None,
    ) -> None:
        """Denetim kaydını kapatır."""
        if call_id is None or not self._db.available:
            return
        try:
            async with self._db.session() as session:
                await ToolCallRepository(session).finish(
                    call_id,
                    status=status,
                    result=_truncate(result),
                    error=error,
                    duration_ms=duration_ms,
                    approved=approved,
                )
        except Exception as exc:
            logger.warning("tool_audit_finish_failed", error=str(exc))

def _truncate(result: dict[str, Any] | None, limit: int = 20000) -> dict[str, Any]:
    """Denetim kaydına yazılacak sonucu makul boyuta indirir."""
    if not result:
        return {}
    import json

    try:
        encoded = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"_repr": str(result)[:limit]}
    if len(encoded) <= limit:
        return result
    return {"_truncated": True, "_preview": encoded[:limit]}
