"""Host köprüsü yetenek el sıkışması ve iptal."""

from __future__ import annotations

import asyncio

import pytest
from app.core.errors import HostBridgeUnavailableError
from app.services.tools.host_bridge import (
    MCP_BRIDGE_TIMEOUT_SECONDS,
    MCP_HOST_TOOLS,
    HostBridge,
    resolve_host_tool_timeout,
)

class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        return None

@pytest.mark.asyncio
async def test_yetenek_ilanindan_sonra_olmayan_arac_reddedilir() -> None:
    bridge = HostBridge(default_timeout=1.0)
    socket = _FakeSocket()
    await bridge.attach(socket, info={"platform": "win32", "version": "0.7.1"})
    bridge.set_capabilities(
        {
            "type": "host_capabilities",
            "tools": ["clipboard_read", "get_selected_text"],
            "features": {"cancel": True, "mcp_list": True},
            "mcp": {"enabled": True, "servers": [{"id": "files", "advertised": ["read"]}]},
            "platform": "win32",
            "version": "0.7.1",
        }
    )
    snap = bridge.snapshot()
    assert "clipboard_read" in snap["tools"]
    assert snap["client"]["version"] == "0.7.1"
    assert snap["mcp"]["enabled"] is True

    with pytest.raises(HostBridgeUnavailableError, match="tanımlı değil|ilan edilmemiş"):
        await bridge.call("run_powershell", {"command": "Get-Date"})

@pytest.mark.asyncio
async def test_zaman_asimi_host_tool_cancel_gonderir() -> None:
    bridge = HostBridge(default_timeout=0.05)
    socket = _FakeSocket()
    await bridge.attach(socket, info={"platform": "win32"})
    with pytest.raises(HostBridgeUnavailableError, match="cevap vermedi"):
        await bridge.call("get_cpu_usage", {})
    assert any(item.get("type") == "host_tool_cancel" for item in socket.sent)

def test_kopuk_snapshot_down() -> None:
    bridge = HostBridge()
    snap = bridge.snapshot()
    assert snap["state"] == "down"
    assert snap["healthy"] is False
    assert snap["connected"] is False

def test_devre_esikten_sonra_degraded() -> None:
    from app.services.tools.policy import CIRCUIT_FAILURE_THRESHOLD

    bridge = HostBridge()
    bridge._socket = object()  # type: ignore[assignment]
    bridge._last_seen = __import__("time").monotonic()
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        bridge.record_failure()
    assert bridge.circuit_open is True
    assert bridge.snapshot()["state"] == "degraded"
    assert bridge.snapshot()["circuit_open"] is True

def test_yarim_acik_soguma_sonrasi_probe() -> None:
    from app.services.tools.policy import CIRCUIT_COOLDOWN_SECONDS, CIRCUIT_FAILURE_THRESHOLD

    bridge = HostBridge()
    bridge._socket = object()  # type: ignore[assignment]
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        bridge.record_failure()
    assert bridge.circuit_open is True
    bridge._circuit_opened_at = __import__("time").monotonic() - (CIRCUIT_COOLDOWN_SECONDS + 0.1)
    bridge._maybe_half_open()
    assert bridge.circuit_open is False

def test_mcp_kopru_suresi_diger_araclari_sismez() -> None:
    assert resolve_host_tool_timeout("get_cpu_usage", 60.0, 60.0) == 60.0
    assert resolve_host_tool_timeout("clipboard_read", None, 60.0) == 60.0
    assert resolve_host_tool_timeout("mcp_call", 60.0, 60.0) == MCP_BRIDGE_TIMEOUT_SECONDS
    assert resolve_host_tool_timeout("mcp_list_tools", None, 60.0) == MCP_BRIDGE_TIMEOUT_SECONDS
    assert resolve_host_tool_timeout("mcp_call", 120.0, 60.0) == 120.0
    assert MCP_BRIDGE_TIMEOUT_SECONDS >= 65.0
    assert MCP_HOST_TOOLS == frozenset({"mcp_call", "mcp_list_tools"})

@pytest.mark.asyncio
async def test_mcp_call_timeout_ms_en_az_70s_digerleri_60s() -> None:
    bridge = HostBridge(default_timeout=60.0)
    socket = _FakeSocket()
    await bridge.attach(socket, info={"platform": "win32"})

    async def finish(tool_name: str) -> None:
        await asyncio.sleep(0.01)
        request = next(item for item in socket.sent if item.get("tool_name") == tool_name)
        bridge.resolve({"request_id": request["request_id"], "success": True, "result": {}})

    task = asyncio.create_task(finish("get_cpu_usage"))
    await bridge.call("get_cpu_usage", {}, timeout_seconds=60.0)
    await task
    cpu = next(item for item in socket.sent if item.get("tool_name") == "get_cpu_usage")
    assert cpu["timeout_ms"] == 60_000

    task = asyncio.create_task(finish("mcp_call"))
    await bridge.call("mcp_call", {"server": "docs"}, timeout_seconds=60.0)
    await task
    mcp = next(item for item in socket.sent if item.get("tool_name") == "mcp_call")
    assert mcp["timeout_ms"] == int(MCP_BRIDGE_TIMEOUT_SECONDS * 1000)
    assert mcp["timeout_ms"] >= 70_000

@pytest.mark.asyncio
async def test_mcp_zaman_asimi_devreyi_acmaz(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = HostBridge(default_timeout=60.0)
    socket = _FakeSocket()
    await bridge.attach(socket, info={"platform": "win32"})

    async def expire(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError()

    monkeypatch.setattr("app.services.tools.host_bridge.asyncio.wait_for", expire)
    for _ in range(3):
        with pytest.raises(HostBridgeUnavailableError, match="cevap vermedi"):
            await bridge.call("mcp_list_tools", {"server": "docs"}, timeout_seconds=60.0)
    assert bridge.circuit_open is False
    assert any(item.get("type") == "host_tool_cancel" for item in socket.sent)

@pytest.mark.asyncio
async def test_tur_iptali_mcp_host_tool_cancel_gonderir() -> None:
    bridge = HostBridge(default_timeout=5.0)
    socket = _FakeSocket()
    await bridge.attach(socket, info={"platform": "win32"})
    task = asyncio.create_task(bridge.call("mcp_call", {"server": "docs", "tool": "query-docs"}))
    for _ in range(20):
        if any(item.get("type") == "host_tool_request" for item in socket.sent):
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert any(item.get("type") == "host_tool_cancel" for item in socket.sent)
    assert bridge.circuit_open is False

@pytest.mark.asyncio
async def test_eski_soket_detach_yeni_rpc_oldurmez() -> None:
    bridge = HostBridge(default_timeout=1.0)
    old = _FakeSocket()
    new = _FakeSocket()
    await bridge.attach(old, info={"platform": "win32"})
    await bridge.attach(new, info={"platform": "win32", "version": "next"})
    await bridge.detach(old)
    assert bridge.connected is True
    assert bridge.client_info.get("version") == "next"
