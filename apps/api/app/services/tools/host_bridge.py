"""Host köprüsü — backend ↔ Electron main process RPC'si.

Backend Linux container içinde çalıştığı için Windows tarafındaki işlemleri
(program açma, pano, ekran görüntüsü, GPU metrikleri…) doğrudan yapamaz. Bu
köprü, Electron uygulamasının ``/ws/host`` üzerinden kurduğu tekil bağlantı
üstünden korelasyon kimlikli istek/cevap alışverişi sağlar.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from app.core.errors import HostBridgeUnavailableError
from app.core.logging import get_logger
from app.schemas.tools import HostToolRequest
from app.services.tools.policy import (
    CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD,
    STALE_AFTER_SECONDS,
)

logger = get_logger(__name__)

MCP_HOST_TOOLS = frozenset({"mcp_call", "mcp_list_tools"})
MCP_BRIDGE_TIMEOUT_SECONDS = 70.0

def resolve_host_tool_timeout(
    tool_name: str,
    requested: float | None = None,
    default: float = 60.0,
) -> float:
    """Diğer host araçları 60s kalır; MCP init+rpc bütçesinin altına inmez."""
    base = default if requested is None or requested <= 0 else float(requested)
    if tool_name in MCP_HOST_TOOLS:
        return max(base, MCP_BRIDGE_TIMEOUT_SECONDS)
    return base

@dataclass(slots=True)
class _Pending:
    future: asyncio.Future[dict[str, Any]]
    generation: int

class HostBridge:
    """Electron ile kurulan tekil WebSocket köprüsü."""

    def __init__(self, default_timeout: float = 60.0) -> None:
        self._socket: WebSocket | None = None
        self._pending: dict[str, _Pending] = {}
        self._default_timeout = default_timeout
        self._lock = asyncio.Lock()
        self._client_info: dict[str, Any] = {}
        self._last_seen: float | None = None
        self._generation = 0
        self._socket_generation = 0
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

        self.last_metrics: dict[str, Any] | None = None

        self.capabilities: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        """Masaüstü uygulaması bağlı mı?"""
        return self._socket is not None

    @property
    def circuit_open(self) -> bool:
        """Zombi sokette fail-fast: bağlı görünür ama RPC üst üste düşer."""
        return self.connected and self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD

    @property
    def stale(self) -> bool:
        """Metrik/yanıt gelmeden uzun süre geçmişse sağlıksız."""
        if self._last_seen is None or not self.connected:
            return False
        return (time.monotonic() - self._last_seen) > STALE_AFTER_SECONDS

    def touch(self) -> None:
        """Son görülme zamanını günceller (mevcut protokol mesajlarında)."""
        if self._socket is not None:
            self._last_seen = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        """Sağlık özeti — Electron sözleşmesini değiştirmez."""
        age = None if self._last_seen is None else round(time.monotonic() - self._last_seen, 3)
        if not self.connected:
            state = "down"
        elif self.circuit_open or self.stale:
            state = "degraded"
        else:
            state = "up"
        return {
            "connected": self.connected,
            "healthy": state == "up",
            "state": state,
            "pending": len(self._pending),
            "last_seen_seconds": age,
            "circuit_open": self.circuit_open,
            "consecutive_failures": self._consecutive_failures,
            "client": dict(self._client_info),
            "tools": list(self.capabilities.get("tools") or []),
            "features": dict(self.capabilities.get("features") or {}),
            "mcp": dict(self.capabilities.get("mcp") or {}),
        }

    @property
    def client_info(self) -> dict[str, Any]:
        """Bağlı istemcinin bildirdiği bilgiler."""
        return dict(self._client_info)

    async def attach(self, websocket: WebSocket, info: dict[str, Any] | None = None) -> None:
        """Yeni bağlantıyı kaydeder (önceki bağlantı kapatılır)."""
        async with self._lock:
            previous_generation = self._socket_generation
            if self._socket is not None:
                with suppress(RuntimeError):
                    await self._socket.close(code=1000, reason="Yeni bağlantı açıldı")
            self._generation += 1
            self._socket = websocket
            self._socket_generation = self._generation
            self._client_info = info or {}
            self._last_seen = time.monotonic()
            self._consecutive_failures = 0
            self._circuit_opened_at = None
            self.capabilities = {}
        self._fail_pending(
            previous_generation, HostBridgeUnavailableError("Masaüstü bağlantısı yenilendi.")
        )
        logger.info("host_bridge_connected", info=self._client_info)

    async def detach(self, websocket: WebSocket) -> None:
        """Bağlantı koptuğunda temizlik yapar.

        Yalnızca bu sokete ait bekleyen çağrılar iptal edilir; yeni bağlantının
        RPC'leri (HANDOFF: çift soket) yanlışlıkla öldürülmez.
        """
        generation = 0
        async with self._lock:
            if self._socket is websocket:
                generation = self._socket_generation
                self._socket = None
                self._client_info = {}
                self.last_metrics = None
                self._last_seen = None
                self.capabilities = {}
        if generation:
            self._fail_pending(
                generation, HostBridgeUnavailableError("Masaüstü bağlantısı koptu.")
            )
            logger.info("host_bridge_disconnected")

    def _fail_pending(self, generation: int, exc: HostBridgeUnavailableError) -> None:
        """Belirli nesile ait bekleyen future'ları hata ile kapatır."""
        for request_id, pending in list(self._pending.items()):
            if pending.generation != generation:
                continue
            self._pending.pop(request_id, None)
            if not pending.future.done():
                pending.future.set_exception(exc)

    def record_success(self) -> None:
        """Başarılı RPC sonrası devre kesiciyi sıfırlar."""
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def record_failure(self) -> None:
        """Başarısız RPC sayacını artırır."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
            self._circuit_opened_at = time.monotonic()

    def _maybe_half_open(self) -> None:
        """Soğuma sonrası tek denemeye izin verir (yarım-açık)."""
        if (
            self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD
            and self._circuit_opened_at is not None
            and (time.monotonic() - self._circuit_opened_at) >= CIRCUIT_COOLDOWN_SECONDS
        ):
            self._consecutive_failures = CIRCUIT_FAILURE_THRESHOLD - 1
            self._circuit_opened_at = None

    async def call(
        self, tool_name: str, arguments: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> dict[str, Any]:
        """Host tarafında bir araç çalıştırır ve sonucu bekler.

        Raises:
            HostBridgeUnavailableError: Masaüstü uygulaması bağlı değilse veya
                zaman aşımı olursa.
        """
        self._maybe_half_open()
        if self.circuit_open:
            raise HostBridgeUnavailableError(
                "Masaüstü köprüsü geçici olarak durduruldu (ardışık hatalar). "
                "Uryx masaüstü uygulamasını yeniden bağlayın.",
                details={"retryable": False, "reason": "circuit_open"},
            )

        tools = self._client_info.get("tools")
        if isinstance(tools, list) and tools and tool_name not in tools:
            raise HostBridgeUnavailableError(
                f"'{tool_name}' bağlı masaüstü sürümünde tanımlı değil.",
                details={"retryable": False, "reason": "capability_missing"},
            )

        socket = self._socket
        generation = self._socket_generation
        if socket is None:
            self.record_failure()
            raise HostBridgeUnavailableError(details={"retryable": True, "reason": "disconnected"})

        advertised = self.capabilities.get("tools")
        if isinstance(advertised, list) and advertised and tool_name not in advertised:
            raise HostBridgeUnavailableError(
                f"'{tool_name}' bağlı masaüstünde ilan edilmemiş.",
                details={"retryable": False, "reason": "unknown_host_tool"},
            )

        request_id = str(uuid.uuid4())
        timeout_seconds = resolve_host_tool_timeout(
            tool_name, timeout_seconds, self._default_timeout
        )
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = _Pending(future=future, generation=generation)

        payload = HostToolRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            timeout_ms=int(timeout_seconds * 1000),
        )

        try:
            await socket.send_json(payload.model_dump())
            self.touch()
        except (RuntimeError, OSError) as exc:
            self._pending.pop(request_id, None)
            self.record_failure()
            raise HostBridgeUnavailableError(
                "Masaüstü uygulamasına istek gönderilemedi.",
                details={"retryable": True, "reason": "send_failed"},
            ) from exc

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:

            if tool_name not in MCP_HOST_TOOLS:
                self.record_failure()
            await self.cancel(request_id)
            raise HostBridgeUnavailableError(
                f"'{tool_name}' aracı {timeout_seconds:.0f} saniyede cevap vermedi.",
                details={"retryable": False, "reason": "timeout"},
            ) from exc
        except asyncio.CancelledError:

            await self.cancel(request_id)
            raise
        except HostBridgeUnavailableError:
            self.record_failure()
            raise
        else:
            self.record_success()
            self.touch()
            return result
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, message: dict[str, Any]) -> None:
        """Electron'dan gelen cevabı bekleyen çağrıya iletir."""
        request_id = str(message.get("request_id", ""))
        pending = self._pending.get(request_id)
        if pending is None or pending.future.done():
            return
        self.touch()
        pending.future.set_result(
            {
                "success": bool(message.get("success", False)),
                "result": message.get("result") or {},
                "error": message.get("error"),
            }
        )

    def update_hello(self, payload: dict[str, Any]) -> None:
        """Electron'un yetenek el sıkışmasını istemci bilgisine birleştirir."""
        self.touch()
        if not payload:
            return
        merged = dict(self._client_info)
        for key, value in payload.items():
            if key in {"type"} or value is None:
                continue
            merged[key] = value
        self._client_info = merged

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """Host'un push ettiği sistem metriklerini saklar."""
        self.last_metrics = metrics
        self.touch()

    def set_capabilities(self, payload: dict[str, Any]) -> None:
        """Electron'un yetenek ilanını kaydeder."""
        tools = payload.get("tools")
        features = payload.get("features")
        mcp = payload.get("mcp")
        self.capabilities = {
            "tools": [str(name) for name in tools] if isinstance(tools, list) else [],
            "features": dict(features) if isinstance(features, dict) else {},
            "mcp": dict(mcp) if isinstance(mcp, dict) else {},
            "platform": str(payload.get("platform") or self._client_info.get("platform") or ""),
            "version": str(payload.get("version") or self._client_info.get("version") or ""),
            "arch": str(payload.get("arch") or ""),
        }
        self.update_hello(payload)

    async def cancel(self, request_id: str) -> bool:
        """Host'taki devam eden aracı iptal etmesini ister (OI timeout kalıbı)."""
        if not request_id:
            return False
        return await self.notify({"type": "host_tool_cancel", "request_id": request_id})

    async def notify(self, event: dict[str, Any]) -> bool:
        """Host'a tek yönlü bildirim gönderir."""
        socket = self._socket
        if socket is None:
            return False
        try:
            await socket.send_json(event)
            self.touch()
            return True
        except (RuntimeError, OSError):
            return False
