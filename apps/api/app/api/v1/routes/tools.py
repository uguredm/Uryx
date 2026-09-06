"""Araç (tool calling) endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import DatabaseDep, ExecutorDep, HostBridgeDep, RegistryDep
from app.core.errors import ToolNotAllowedError
from app.core.security import require_token
from app.db.repositories.conversation import ToolCallRepository
from app.schemas.common import OkResponse
from app.schemas.tools import (
    HostBridgeSnapshot,
    ToolInvocation,
    ToolListResponse,
    ToolPrepareResponse,
    ToolResult,
)

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_token)])

@router.get("", response_model=ToolListResponse, summary="Araçları listele")
async def list_tools(registry: RegistryDep, host_bridge: HostBridgeDep) -> ToolListResponse:
    """Allowlist'teki tüm araçları ve host köprüsü durumunu döndürür."""
    snap = host_bridge.snapshot()
    return ToolListResponse(
        tools=registry.all(),
        host_bridge_connected=host_bridge.connected,
        host_bridge=HostBridgeSnapshot.model_validate(snap),
    )

@router.post("/prepare", response_model=ToolPrepareResponse, summary="Aracı hazırla")
async def prepare_tool(payload: ToolInvocation, executor: ExecutorDep) -> ToolPrepareResponse:
    """Çalıştırmadan politika kararı ve (gerekirse) onay bileti üretir.

    HIGH riskli REST çağrıları ``POST /execute`` öncesi bu bilet olmadan
    ``confirmed=true`` ile geçemez.
    """
    return executor.prepare(
        payload.tool_name,
        payload.arguments,
        conversation_id=payload.conversation_id,
    )

@router.post("/execute", response_model=ToolResult, summary="Aracı çalıştır")
async def execute_tool(payload: ToolInvocation, executor: ExecutorDep) -> ToolResult:
    """Bir aracı doğrudan çalıştırır.

    Onay gerektiren araçlarda ``confirmed=true`` gönderilmelidir; aksi hâlde
    ``428 Precondition Required`` döner. Yüksek riskli araçlar için ayrıca
    ``POST /tools/prepare`` bileti veya eşleşen parmak izi gerekir.
    """
    return await executor.execute(
        payload.tool_name,
        payload.arguments,
        conversation_id=payload.conversation_id,
        confirmed=payload.confirmed,
        confirmation_ticket=payload.confirmation_ticket,
        expected_fingerprint=payload.expected_fingerprint,
    )

@router.post("/{tool_name}/enabled", response_model=OkResponse, summary="Aracı aç/kapat")
async def set_tool_enabled(
    tool_name: str, registry: RegistryDep, enabled: bool = Query(default=True)
) -> OkResponse:
    """Bir aracı etkinleştirir veya devre dışı bırakır.

    Varlık kontrolü için ``has()`` kullanılır; ``get()`` devre dışı araçlar için
    hata fırlattığından kapatılan bir araç bir daha açılamazdı.
    """
    if not registry.has(tool_name):
        raise ToolNotAllowedError(
            f"'{tool_name}' adında bir araç yok veya izin listesinde değil.",
            details={"available": [t.name for t in registry.all()]},
        )
    registry.set_enabled(tool_name, enabled)
    return OkResponse(message=f"'{tool_name}' {'etkin' if enabled else 'devre dışı'}.")

@router.get("/history", summary="Son araç çağrıları")
async def tool_history(
    database: DatabaseDep, limit: int = Query(default=50, ge=1, le=500)
) -> list[dict[str, object]]:
    """Denetim kaydındaki son araç çağrılarını döndürür."""
    async with database.session() as session:
        calls = await ToolCallRepository(session).list_recent(limit=limit)
    return [
        {
            "id": c.id,
            "conversation_id": c.conversation_id,
            "tool_name": c.tool_name,
            "arguments": c.arguments,
            "status": c.status.value if hasattr(c.status, "value") else c.status,
            "risk_level": c.risk_level,
            "required_confirmation": c.required_confirmation,
            "approved": c.approved,
            "duration_ms": c.duration_ms,
            "error": c.error,
            "created_at": c.created_at.isoformat(),
        }
        for c in calls
    ]
