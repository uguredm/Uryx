"""food_barcode — Open Food Facts, sabit host, ağ yok."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from app.core.errors import ToolExecutionError
from app.services.llm.prompts import BASE_SYSTEM_PROMPT
from app.services.tools.policy import IDEMPOTENT_TOOLS, normalize_tool_name
from app.services.tools.registry import ToolRegistry
from app.services.web.food import food_barcode_url, lookup_food_barcode, normalize_barcode

def test_barkod_alias() -> None:
    assert normalize_barcode("3017620422003") == "3017620422003"
    assert "world.openfoodfacts.org/api/v2/product/3017620422003" in food_barcode_url(
        "3017620422003"
    )
    with pytest.raises(ToolExecutionError):
        normalize_barcode("abc")
    assert ToolRegistry().get("food_barcode") is not None
    assert "food_barcode" in IDEMPOTENT_TOOLS
    assert normalize_tool_name("barkod") == "food_barcode"
    assert "food_barcode" in BASE_SYSTEM_PROMPT

async def test_urun_ve_yonlendirme() -> None:
    class Ok:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "status": 1,
                "product": {
                    "product_name": "Nutella",
                    "brands": "Ferrero",
                    "quantity": "400 g",
                    "nutriscore_grade": "e",
                    "nova_group": 4,
                    "allergens_tags": ["en:nuts", "en:milk"],
                },
            }

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Ok:
            assert "world.openfoodfacts.org" in url
            return Ok()

    with patch("app.services.web.food.httpx.AsyncClient", Client):
        out = await lookup_food_barcode("3017620422003")
    assert out["name"] == "Nutella"
    assert "nuts" in out["allergens"]

async def test_yonlendirme_red() -> None:
    class Redirect:
        status_code = 302
        headers: ClassVar[dict[str, str]] = {
            "location": "https://world.openbeautyfacts.org/api/v2/product/1"
        }

        def json(self) -> dict[str, str]:
            return {}

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def get(self, url: str) -> Redirect:
            return Redirect()

    with (
        patch("app.services.web.food.httpx.AsyncClient", Client),
        pytest.raises(ToolExecutionError, match="yönlendirme"),
    ):
        await lookup_food_barcode("8710447445990")
