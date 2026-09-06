"""Yapılandırılmış loglama (structlog).

Hassas veriler (şifre, token, api key…) loga yazılmadan önce maskelenir.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|passwd|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
]

MASK = "***"

def _mask_value(value: Any) -> Any:
    """Tek bir değeri maskeler."""
    if isinstance(value, str):
        masked = value
        for pattern in SENSITIVE_PATTERNS:
            masked = pattern.sub(MASK, masked)
        return masked
    return value

def redact_processor(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Hassas alanları maskeleyen structlog processor'ü."""

    def _walk(obj: Any, depth: int = 0) -> Any:
        if depth > 6:
            return obj
        if isinstance(obj, dict):
            return {
                k: (MASK if SENSITIVE_KEYS.search(str(k)) else _walk(v, depth + 1))
                for k, v in obj.items()
            }
        if isinstance(obj, list | tuple):
            return type(obj)(_walk(v, depth + 1) for v in obj)
        return _mask_value(obj)

    return _walk(event_dict)  # type: ignore[return-value]

def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Uygulama genelinde loglamayı yapılandırır.

    Args:
        level: Log seviyesi (``DEBUG`` … ``CRITICAL``).
        json_output: ``True`` ise JSON, aksi halde renkli konsol çıktısı.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_processor,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """İsimlendirilmiş bir logger döndürür."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
