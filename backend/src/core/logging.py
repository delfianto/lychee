"""Structured logging via structlog."""

import logging
from typing import Any

import structlog

from src.core.config import settings


def configure_logging() -> None:
    """Configure structlog once at startup (console or JSON per settings)."""
    level = logging.getLevelNamesMapping()[settings.log_level]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
