"""Hesap / birim aracı — AST, kabuk yok."""

from __future__ import annotations

import pytest
from app.core.errors import ToolExecutionError
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.tools.calc import convert_units, evaluate_expression, run_calculate
from app.services.tools.intent import is_calculate_request, match_known_app
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry

def test_toplama_ve_turkce_ondalik() -> None:
    assert evaluate_expression("2+2") == 4
    assert evaluate_expression("1,5*4") == 6
    assert evaluate_expression("sqrt(9)+pow(2,3)") == 11

def test_sifira_bolme_ve_yasak_sozdizimi() -> None:
    with pytest.raises(ToolExecutionError, match="Sıfıra"):
        evaluate_expression("1/0")
    with pytest.raises(ToolExecutionError):
        evaluate_expression("__import__('os').system('dir')")
    with pytest.raises(ToolExecutionError):
        evaluate_expression("abs.__class__")

def test_us_siniri() -> None:
    with pytest.raises(ToolExecutionError, match="Üs"):
        evaluate_expression("2**20")

def test_km_mil_ve_sicaklik() -> None:
    miles = convert_units(value=100, from_unit="km", to_unit="mil")
    assert 62.1 < miles < 62.2
    assert convert_units(value=0, from_unit="c", to_unit="f") == 32
    assert convert_units(value=100, from_unit="santigrat", to_unit="fahrenheit") == 212

def test_farkli_boyut_ve_doviz_yok() -> None:
    with pytest.raises(ToolExecutionError, match="boyutta"):
        convert_units(value=1, from_unit="km", to_unit="kg")
    with pytest.raises(ToolExecutionError, match="döviz"):
        convert_units(value=1, from_unit="usd", to_unit="try")

def test_run_calculate_eval_ve_convert() -> None:
    eval_out = run_calculate({"expression": "(3+5)*2"})
    assert eval_out["ok"] is True
    assert eval_out["kind"] == "eval"
    assert eval_out["result"] == 16
    conv = run_calculate({"value": 1, "from_unit": "kg", "to_unit": "g"})
    assert conv["result"] == 1000

def test_registry_ve_alias() -> None:
    registry = ToolRegistry()
    tool = registry.get("calculate")
    assert tool.execution is ExecutionTarget.BACKEND
    assert tool.risk is RiskLevel.LOW
    assert "open_application" in tool.description
    assert "web_search" in tool.description
    assert "calculate" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("hesapla") == "calculate"
    assert normalize_tool_name("convert_units") == "calculate"

def test_niyet_hesap_uygulama_degil() -> None:
    assert is_calculate_request("2+2 kaç eder") is True
    assert is_calculate_request("100 km kaç mil") is True
    assert is_calculate_request("hesapla 15*3") is True
    assert is_calculate_request("hesap makinesini aç") is False
    assert is_calculate_request("dolar kaç TL") is False
    assert is_calculate_request("bitcoin fiyatı ne kadar") is False
    assert match_known_app("hesap makinesini aç") == "calc"
