"""Yerel IBAN doğrulama — ağ yok."""

from __future__ import annotations

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.tools.iban import check_iban, normalize_iban, run_iban_check
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry

_TR_OK = "TR330006100519786457841326"

def test_tr_gecerli_ve_bosluk() -> None:
    out = check_iban("TR33 0006 1005 1978 6457 8413 26")
    assert out["valid"] is True
    assert out["country"] == "TR"
    assert out["iban"] == _TR_OK
    assert out["formatted"].startswith("TR33")

def test_checksum_ve_uzunluk_red() -> None:
    bad = check_iban("TR330006100519786457841327")
    assert bad["valid"] is False
    assert "kontrol" in bad["reason"]
    short_tr = check_iban("DE89370400440532013000")
    assert short_tr["valid"] is True
    with pytest.raises(ToolExecutionError):
        normalize_iban("")
    with pytest.raises(ToolExecutionError):
        normalize_iban("javascript:alert(1)")
    with pytest.raises(ToolExecutionError):
        normalize_iban("TR")

def test_run_ve_registry() -> None:
    out = run_iban_check({"iban": _TR_OK})
    assert out["ok"] is True
    tool = ToolRegistry().get("iban_check")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "iban_check" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("iban") == "iban_check"
    assert normalize_tool_name("iban_dogrula") == "iban_check"
