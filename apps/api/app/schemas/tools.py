"""Araç (tool calling) şemaları."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class RiskLevel(str, Enum):
    """Aracın risk seviyesi.

    ``LOW``    → onay gerekmez (salt okunur / etkisiz).
    ``MEDIUM`` → onay gerekir (sistemde görünür değişiklik yapar).
    ``HIGH``   → onay gerekir (geri alınamaz / güvenlik etkisi olabilir).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ExecutionTarget(str, Enum):
    """Aracın nerede çalıştığı."""

    BACKEND = "backend"

    HOST = "host"

class ToolParameter(BaseModel):
    """Araç parametresi tanımı."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    default: Any | None = None

class ToolDefinition(BaseModel):
    """Bir aracın tam tanımı (allowlist kaydı)."""

    name: str
    display_name: str
    description: str
    category: str = "general"
    risk: RiskLevel = RiskLevel.LOW
    execution: ExecutionTarget = ExecutionTarget.BACKEND
    parameters: list[ToolParameter] = Field(default_factory=list)
    impact: str = ""
    enabled: bool = True

    def to_openai_schema(self) -> dict[str, Any]:
        """OpenAI/vLLM tool-calling formatına dönüştürür."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.parameters:
            schema: dict[str, Any] = {"type": param.type, "description": param.description}
            if param.enum:
                schema["enum"] = param.enum
            properties[param.name] = schema
            if param.required:
                required.append(param.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

class ToolInvocation(BaseModel):
    """Bir araç çağrısı isteği."""

    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None

    confirmed: bool = False

    confirmation_ticket: str | None = None

    expected_fingerprint: str | None = None

class ToolResult(BaseModel):
    """Araç çalıştırma sonucu."""

    call_id: str
    tool_name: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    requires_confirmation: bool = False

    retries: int = 0

    def to_llm_content(self) -> str:
        """LLM'e geri verilecek metin gösterimi (sırlar maskeli)."""
        import json

        from app.services.tools.policy import (
            redact_for_llm,
            tool_error_observation,
            wrap_untrusted_observation,
        )

        payload = (
            self.result
            if self.success
            else tool_error_observation(self.error, self.retries)
        )
        payload = wrap_untrusted_observation(self.tool_name, payload)
        payload = redact_for_llm(payload)
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)[:8000]
        except (TypeError, ValueError):
            return str(payload)[:8000]

class ToolPrepareResponse(BaseModel):
    """REST araç hazırlığı — onay bileti ve etkili risk."""

    tool_name: str
    display_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    risk_level: str
    effective_risk: str
    needs_confirmation: bool
    remember_allowed: bool
    confirmation_ticket: str | None = None
    blocked: bool = False
    block_reason: str | None = None

class HostBridgeSnapshot(BaseModel):
    """Host köprüsü sağlık özeti."""

    connected: bool = False
    healthy: bool = False
    state: str = "down"
    pending: int = 0
    last_seen_seconds: float | None = None
    circuit_open: bool = False
    consecutive_failures: int = 0
    client: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    mcp: dict[str, Any] = Field(default_factory=dict)

class ToolListResponse(BaseModel):
    """Kayıtlı araçların listesi."""

    tools: list[ToolDefinition]
    host_bridge_connected: bool = False
    host_bridge: HostBridgeSnapshot | None = None

class HostToolRequest(BaseModel):
    """Backend → Electron host aracı çağrısı."""

    type: str = "host_tool_request"
    request_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 60000

class HostToolResponse(BaseModel):
    """Electron → backend host aracı sonucu."""

    type: str = "host_tool_response"
    request_id: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
