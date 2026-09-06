"""Allowlist'li hesap ve birim çevirme — serbest kabuk / eval yok.

AST ile yalnızca sayı, dört işlem ve sabit fonksiyonlar; birimler SI çarpanı
veya sıcaklık formülü. Model Python çalıştıramaz.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

from app.core.errors import ToolExecutionError, ValidationError
from app.core.locale import loc

_MAX_EXPR = 200
_MAX_ABS = 1e15
_MAX_POW_EXP = 12
_MAX_CALL_ARGS = 8

_BIN: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type, Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "pow": pow,
}
_CONSTS = {"pi": math.pi, "e": math.e}

_UNITS: dict[str, tuple[str, float]] = {
    "m": ("length", 1.0),
    "metre": ("length", 1.0),
    "meter": ("length", 1.0),
    "km": ("length", 1000.0),
    "kilometre": ("length", 1000.0),
    "kilometer": ("length", 1000.0),
    "cm": ("length", 0.01),
    "santimetre": ("length", 0.01),
    "mm": ("length", 0.001),
    "milimetre": ("length", 0.001),
    "mi": ("length", 1609.344),
    "mil": ("length", 1609.344),
    "mile": ("length", 1609.344),
    "miles": ("length", 1609.344),
    "yd": ("length", 0.9144),
    "yard": ("length", 0.9144),
    "ft": ("length", 0.3048),
    "feet": ("length", 0.3048),
    "foot": ("length", 0.3048),
    "ayak": ("length", 0.3048),
    "in": ("length", 0.0254),
    "inch": ("length", 0.0254),
    "inc": ("length", 0.0254),
    "inç": ("length", 0.0254),
    "kg": ("mass", 1.0),
    "kilogram": ("mass", 1.0),
    "g": ("mass", 0.001),
    "gram": ("mass", 0.001),
    "mg": ("mass", 1e-6),
    "lb": ("mass", 0.45359237),
    "lbs": ("mass", 0.45359237),
    "pound": ("mass", 0.45359237),
    "libre": ("mass", 0.45359237),
    "oz": ("mass", 0.028349523125),
    "ons": ("mass", 0.028349523125),
    "t": ("mass", 1000.0),
    "ton": ("mass", 1000.0),
    "tonne": ("mass", 1000.0),
    "l": ("volume", 0.001),
    "lt": ("volume", 0.001),
    "litre": ("volume", 0.001),
    "liter": ("volume", 0.001),
    "ml": ("volume", 1e-6),
    "mililitre": ("volume", 1e-6),
    "m3": ("volume", 1.0),
    "gal": ("volume", 0.003785411784),
    "gallon": ("volume", 0.003785411784),
    "galon": ("volume", 0.003785411784),
    "s": ("time", 1.0),
    "sn": ("time", 1.0),
    "sec": ("time", 1.0),
    "saniye": ("time", 1.0),
    "min": ("time", 60.0),
    "dakika": ("time", 60.0),
    "h": ("time", 3600.0),
    "saat": ("time", 3600.0),
    "hour": ("time", 3600.0),
    "d": ("time", 86400.0),
    "gun": ("time", 86400.0),
    "gün": ("time", 86400.0),
    "day": ("time", 86400.0),
    "kmh": ("speed", 1 / 3.6),
    "km/h": ("speed", 1 / 3.6),
    "kph": ("speed", 1 / 3.6),
    "ms": ("speed", 1.0),
    "m/s": ("speed", 1.0),
    "mph": ("speed", 0.44704),
    "c": ("temp", 0.0),
    "celsius": ("temp", 0.0),
    "santigrat": ("temp", 0.0),
    "centigrade": ("temp", 0.0),
    "f": ("temp", 0.0),
    "fahrenheit": ("temp", 0.0),
    "k": ("temp", 0.0),
    "kelvin": ("temp", 0.0),
}

def _normalize_unit(raw: str) -> str:
    text = re.sub(r"\s+", "", str(raw).strip().casefold().replace("°", ""))
    text = text.replace("km/saat", "kmh").replace("km/sa", "kmh")
    return text

def _finite(value: float) -> float:
    if not math.isfinite(value) or abs(value) > _MAX_ABS:
        raise ToolExecutionError(
            loc("Sonuç sayısal sınırın dışında.", "Result is outside the numeric limit.")
        )
    return float(value)

def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(
        node.value, bool
    ):
        return _finite(float(node.value))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _finite(_UNARY[type(node.op)](_eval_node(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if type(node.op) is ast.Pow and abs(right) > _MAX_POW_EXP:
            raise ToolExecutionError(loc("Üs çok büyük.", "Exponent is too large."))
        if type(node.op) in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ToolExecutionError(loc("Sıfıra bölme.", "Division by zero."))
        return _finite(_BIN[type(node.op)](left, right))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id
        if name not in _FUNCS:
            raise ToolExecutionError(
                loc(
                    f"'{name}' fonksiyonuna izin yok.",
                    f"Function '{name}' is not allowed.",
                )
            )
        if len(node.args) > _MAX_CALL_ARGS:
            raise ToolExecutionError(loc("Çok fazla argüman.", "Too many arguments."))
        args = [_eval_node(arg) for arg in node.args]
        if name == "pow" and len(args) >= 2 and abs(args[1]) > _MAX_POW_EXP:
            raise ToolExecutionError(loc("Üs çok büyük.", "Exponent is too large."))
        try:
            result = _FUNCS[name](*args)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ToolExecutionError(
                loc("İfade hesaplanamadı.", "Expression could not be evaluated.")
            ) from exc
        return _finite(float(result))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ToolExecutionError(
        loc(
            "İfade yalnızca sayı, + - * / // % ** ve abs/round/min/max/sqrt/pow içerebilir.",
            "Expression may only contain numbers, + - * / // % ** and abs/round/min/max/sqrt/pow.",
        )
    )

def evaluate_expression(expression: str) -> float:
    """Güvenli aritmetik; ``eval`` / isim / öznitelik yok."""
    raw = str(expression).strip()
    if not raw or len(raw) > _MAX_EXPR:
        raise ValidationError("İfade boş veya çok uzun.")
    if re.search(r"[;`$]|__|import|lambda|eval", raw, flags=re.IGNORECASE):
        raise ToolExecutionError(
            loc(
                "İfade izin verilen sözdiziminin dışında.",
                "Expression is outside the allowed syntax.",
            )
        )
    normalized = raw.replace("×", "*").replace("÷", "/").replace(":", "/")
    normalized = re.sub(r"(?<![\w.(])(\d+),(\d+)", r"\1.\2", normalized)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ToolExecutionError(
            loc("İfade çözülemedi.", "Expression could not be parsed.")
        ) from exc
    return _eval_node(tree)

def _to_kelvin(value: float, unit: str) -> float:
    if unit in {"c", "celsius", "santigrat", "centigrade"}:
        return value + 273.15
    if unit in {"f", "fahrenheit"}:
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    if unit in {"k", "kelvin"}:
        return value
    raise ToolExecutionError(
        loc("Bilinmeyen sıcaklık birimi.", "Unknown temperature unit.")
    )

def _from_kelvin(kelvin: float, unit: str) -> float:
    if unit in {"c", "celsius", "santigrat", "centigrade"}:
        return kelvin - 273.15
    if unit in {"f", "fahrenheit"}:
        return (kelvin - 273.15) * 9.0 / 5.0 + 32.0
    if unit in {"k", "kelvin"}:
        return kelvin
    raise ToolExecutionError(
        loc("Bilinmeyen sıcaklık birimi.", "Unknown temperature unit.")
    )

def convert_units(*, value: float, from_unit: str, to_unit: str) -> float:
    """Aynı kategorideki birimleri çevirir; döviz yok."""
    src = _normalize_unit(from_unit)
    dst = _normalize_unit(to_unit)
    if src not in _UNITS or dst not in _UNITS:
        raise ToolExecutionError(
            loc(
                "Birim tanınmıyor. Uzunluk/kütle/hacim/süre/hız/sıcaklık kullan; döviz için fx_rate.",
                "Unit not recognized. Use length/mass/volume/time/speed/temperature; "
                "use fx_rate for currency.",
            )
        )
    src_cat, src_factor = _UNITS[src]
    dst_cat, dst_factor = _UNITS[dst]
    if src_cat != dst_cat:
        raise ToolExecutionError(
            loc(
                "Birimler aynı boyutta olmalı (ör. km→mil, °C→°F).",
                "Units must be the same dimension (e.g. km→mi, °C→°F).",
            )
        )
    if src_cat == "temp":
        return _finite(_from_kelvin(_to_kelvin(float(value), src), dst))
    if dst_factor == 0:
        raise ToolExecutionError(
            loc("Hedef birim geçersiz.", "Target unit is invalid.")
        )
    return _finite(float(value) * src_factor / dst_factor)

def run_calculate(args: dict[str, Any]) -> dict[str, Any]:
    """Araç giriş noktası."""
    from_unit = str(args.get("from_unit") or "").strip()
    to_unit = str(args.get("to_unit") or "").strip()
    expression = str(args.get("expression") or "").strip()
    if from_unit or to_unit:
        if not from_unit or not to_unit:
            raise ValidationError("Çeviride from_unit ve to_unit birlikte gerekir.")
        raw_value = args.get("value", args.get("amount"))
        if raw_value is None and expression:
            value = evaluate_expression(expression)
        elif raw_value is None:
            raise ValidationError("Çeviride value gerekir.")
        else:
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValidationError("value sayı olmalı.") from exc
        result = convert_units(value=value, from_unit=from_unit, to_unit=to_unit)
        return {
            "ok": True,
            "kind": "convert",
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "result": result,
        }
    if not expression:
        raise ValidationError("expression veya birim çevirisi gerekir.")
    result = evaluate_expression(expression)
    display = int(result) if result.is_integer() else result
    return {"ok": True, "kind": "eval", "expression": expression, "result": display}
