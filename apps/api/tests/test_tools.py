"""Araç kayıt defteri ve çalıştırıcı testleri."""

from __future__ import annotations

import pytest
from app.core.errors import (
    ToolConfirmationRequiredError,
    ToolNotAllowedError,
    ValidationError,
)
from app.schemas.tools import ExecutionTarget, RiskLevel
from app.services.tools.registry import ToolRegistry

@pytest.fixture
def registry() -> ToolRegistry:
    """Varsayılan araç kaydı."""
    return ToolRegistry()

class TestAllowlist:
    """Allowlist davranışı."""

    def test_bilinmeyen_arac_reddedilir(self, registry: ToolRegistry) -> None:
        with pytest.raises(ToolNotAllowedError) as excinfo:
            registry.get("rm_rf_everything")
        assert "search_documents" in excinfo.value.details["available"]

    def test_devre_disi_arac_reddedilir(self, registry: ToolRegistry) -> None:
        registry.set_enabled("read_file", False)
        with pytest.raises(ToolNotAllowedError):
            registry.get("read_file")

    def test_tum_araclarin_benzersiz_adi_var(self, registry: ToolRegistry) -> None:
        names = [tool.name for tool in registry.all()]
        assert len(names) == len(set(names))

    def test_riskli_araclar_dogru_isaretlenmis(self, registry: ToolRegistry) -> None:
        for name in (
            "delete_file",
            "kill_process",
            "run_powershell",
            "run_cmd",
            "git_push",
            "mcp_call",
        ):
            assert registry.get(name).risk is RiskLevel.HIGH, name

    def test_salt_okunur_araclar_dusuk_riskli(self, registry: ToolRegistry) -> None:
        for name in ("get_cpu_usage", "get_ram_usage", "read_file", "search_files"):
            assert registry.get(name).risk is RiskLevel.LOW, name

    def test_host_araclari_dogru_hedefe_yonlendirilmis(self, registry: ToolRegistry) -> None:
        assert registry.get("open_application").execution is ExecutionTarget.HOST
        assert registry.get("browser_open").execution is ExecutionTarget.HOST
        assert registry.get("get_selected_text").execution is ExecutionTarget.HOST
        assert registry.get("get_foreground_window").execution is ExecutionTarget.HOST
        assert registry.get("get_display_info").execution is ExecutionTarget.HOST
        assert registry.get("get_idle_time").execution is ExecutionTarget.HOST
        assert registry.get("get_network_interfaces").execution is ExecutionTarget.HOST
        assert registry.get("notify_user").execution is ExecutionTarget.HOST
        assert registry.get("get_docker_engine_status").execution is ExecutionTarget.HOST
        assert registry.get("open_docker_desktop").execution is ExecutionTarget.HOST
        assert registry.get("get_docker_desktop_logs").execution is ExecutionTarget.HOST
        assert registry.get("mcp_list_tools").execution is ExecutionTarget.HOST
        assert registry.get("list_directory").execution is ExecutionTarget.HOST
        assert registry.get("copy_file").execution is ExecutionTarget.HOST
        assert registry.get("move_file").execution is ExecutionTarget.HOST
        assert registry.get("create_directory").execution is ExecutionTarget.HOST
        assert registry.get("get_uptime").execution is ExecutionTarget.HOST
        assert registry.get("get_wifi_status").execution is ExecutionTarget.HOST
        assert registry.get("copy_selected_text").execution is ExecutionTarget.HOST
        assert registry.get("get_volume").execution is ExecutionTarget.HOST
        assert registry.get("lock_workstation").execution is ExecutionTarget.HOST
        assert registry.get("file_exists").execution is ExecutionTarget.HOST
        assert registry.get("is_process_running").execution is ExecutionTarget.HOST
        assert registry.get("list_open_windows").execution is ExecutionTarget.HOST
        assert registry.get("eject_removable_drive").execution is ExecutionTarget.HOST
        assert registry.get("open_windows_settings").execution is ExecutionTarget.HOST
        assert registry.get("docker_list_containers").execution is ExecutionTarget.BACKEND
        assert registry.get("calculate").execution is ExecutionTarget.BACKEND
        assert registry.get("calculate").risk is RiskLevel.LOW
        assert registry.get("iban_check").execution is ExecutionTarget.BACKEND
        assert registry.get("iban_check").risk is RiskLevel.LOW

    def test_outlook_takvim_host_salt_okuma(self, registry: ToolRegistry) -> None:
        for name in ("list_calendar_events", "list_outlook_tasks"):
            tool = registry.get(name)
            assert tool.execution is ExecutionTarget.HOST, name
            assert tool.category == "system", name
            assert tool.risk is RiskLevel.LOW, name

    def test_tarayici_gorsel_getirme_sabit_klasorde_onaysiz_calabilir(
        self, registry: ToolRegistry
    ) -> None:
        assert registry.get("browser_open").risk is RiskLevel.LOW
        assert registry.get("browser_read_page").risk is RiskLevel.LOW
        assert registry.get("browser_save_images").risk is RiskLevel.LOW

    def test_tarayici_form_araclari_host_medium(self, registry: ToolRegistry) -> None:
        listed = registry.get("browser_list_controls")
        assert listed.execution is ExecutionTarget.HOST
        assert listed.category == "web"
        assert listed.risk is RiskLevel.LOW
        for name in ("browser_click", "browser_type", "browser_fill_form"):
            tool = registry.get(name)
            assert tool.execution is ExecutionTarget.HOST, name
            assert tool.category == "web", name
            assert tool.risk is RiskLevel.MEDIUM, name
        assert "collectPageState" not in {tool.name for tool in registry.enabled()}

class TestArgumentValidation:
    """Argüman doğrulama."""

    def test_zorunlu_alan_eksikse_hata(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError, match="zorunlu") as excinfo:
            registry.validate_arguments("open_application", {})
        assert excinfo.value.details["required"] == ["name"]
        assert excinfo.value.details["missing"] == "name"

    def test_bilinmeyen_alanlar_atilir(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments(
            "open_application", {"name": "notepad", "hacker": "payload"}
        )
        assert cleaned == {"name": "notepad"}

    def test_varsayilan_degerler_eklenir(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments("search_files", {"query": "*.pdf"})
        assert cleaned["limit"] == 50

    def test_tip_donusumu_yapilir(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments("kill_process", {"pid": "1234"})
        assert cleaned["pid"] == 1234
        assert isinstance(cleaned["pid"], int)

    def test_gecersiz_tip_reddedilir(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError):
            registry.validate_arguments("kill_process", {"pid": "abc"})

    def test_enum_disi_deger_reddedilir(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError):
            registry.validate_arguments(
                "edit_file", {"path": "a.txt", "content": "x", "mode": "delete"}
            )

    def test_bool_donusumu(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments("docker_list_containers", {"all": "evet"})
        assert cleaned["all"] is True

    def test_string_alana_parcali_liste_birlesir(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments("web_search", {"query": ["İstanbul", " hava"]})
        assert cleaned["query"] == "İstanbul hava"

    def test_commands_alias_command_olur(self, registry: ToolRegistry) -> None:
        cleaned = registry.validate_arguments("run_powershell", {"commands": "Get-Date"})
        assert cleaned["command"] == "Get-Date"

    def test_json_string_dizi_cozulur(self) -> None:
        from app.services.tools.registry import _coerce

        assert _coerce("t", "ext", "array", '["pdf", "txt"]') == ["pdf", "txt"]

class TestConfirmation:
    """Onay kuralları."""

    def test_dusuk_risk_onay_istemez(self, registry: ToolRegistry) -> None:
        assert registry.requires_confirmation("get_cpu_usage") is False

    def test_orta_risk_ayar_acikken_onay_ister(self, registry: ToolRegistry) -> None:
        assert registry.requires_confirmation("open_application", confirmation_enabled=True) is True

    def test_orta_risk_ayar_kapaliyken_onay_istemez(self, registry: ToolRegistry) -> None:
        assert (
            registry.requires_confirmation("open_application", confirmation_enabled=False) is False
        )

    def test_yuksek_risk_ayar_kapali_olsa_da_onay_ister(self, registry: ToolRegistry) -> None:
        assert registry.requires_confirmation("delete_file", confirmation_enabled=False) is True
        assert registry.requires_confirmation("run_powershell", confirmation_enabled=False) is True

class TestOpenAISchema:
    """LLM'e sunulan şema."""

    def test_sema_openai_formatinda(self, registry: ToolRegistry) -> None:
        schemas = registry.openai_schemas()
        assert schemas, "En az bir araç şeması üretilmeli"
        for schema in schemas:
            assert schema["type"] == "function"
            function = schema["function"]
            assert {"name", "description", "parameters"} <= set(function)
            assert function["parameters"]["type"] == "object"

    def test_devre_disi_arac_semaya_girmez(self, registry: ToolRegistry) -> None:
        registry.set_enabled("git_push", False)
        names = {s["function"]["name"] for s in registry.openai_schemas()}
        assert "git_push" not in names

class TestExecutor:
    """Araç çalıştırıcı."""

    async def test_onaysiz_riskli_arac_calistirilamaz(self, container) -> None:
        with pytest.raises(ToolConfirmationRequiredError):
            await container.executor.execute("delete_file", {"path": "C:/tmp/a.txt"})

    async def test_host_koprusu_yoksa_anlamli_hata(self, container) -> None:
        result = await container.executor.execute("get_cpu_usage", {})
        assert result.success is False
        assert "masaüstü" in (result.error or "").lower()

    async def test_backend_araci_calisir(self, container) -> None:
        result = await container.executor.execute("search_documents", {"query": "test"})
        assert result.success is True
        assert result.result["count"] == 0

    async def test_hassas_bilgi_hafizaya_yazilmaz(self, container) -> None:
        args = {"content": "Sunucu şifrem: Abc12345!"}
        prepared = container.executor.prepare("save_memory", args)
        result = await container.executor.execute(
            "save_memory",
            args,
            confirmation_ticket=prepared.confirmation_ticket,
        )
        assert result.success is False
        assert "hassas" in (result.error or "").lower()

    async def test_gecerli_bilgi_hafizaya_yazilir(self, container) -> None:
        args = {
            "content": "Projelerimi Masaüstü/Projeler klasöründe tutuyorum.",
            "category": "folder",
        }
        prepared = container.executor.prepare("save_memory", args)
        result = await container.executor.execute(
            "save_memory",
            args,
            confirmation_ticket=prepared.confirmation_ticket,
        )
        assert result.success is True
        assert result.result["saved"] is True

    async def test_medium_prepare_siz_428(self, container) -> None:
        with pytest.raises(ToolConfirmationRequiredError):
            await container.executor.execute(
                "save_memory",
                {"content": "Projelerimi Masaüstü/Projeler klasöründe tutuyorum."},
            )

    async def test_high_confirmed_true_biletsiz_428(self, container) -> None:
        with pytest.raises(ToolConfirmationRequiredError):
            await container.executor.execute(
                "delete_file",
                {"path": "C:/tmp/a.txt"},
                confirmed=True,
                expected_fingerprint="deadbeef",
            )

    async def test_high_bilet_ile_host_yok_hatasi(self, container) -> None:
        args = {"path": "C:/tmp/a.txt"}
        prepared = container.executor.prepare("delete_file", args)
        assert prepared.needs_confirmation is True
        assert prepared.confirmation_ticket
        result = await container.executor.execute(
            "delete_file", args, confirmation_ticket=prepared.confirmation_ticket
        )
        assert result.success is False
        assert "masaüstü" in (result.error or "").lower()
