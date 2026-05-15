"""Structured JSON logging helpers."""

import json
import logging
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any


request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_BASE_LOGGER_NAME = "queryshield"
_CONFIGURED = False

_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def set_request_id(request_id: str | None) -> None:
    """Set the request id for log records emitted in the current context."""
    request_id_context.set(request_id)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None)
            or request_id_context.get(),
        }

        if record.exc_info:
            log_entry["traceback"] = "".join(traceback.format_exception(*record.exc_info))

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key in log_entry:
                continue
            log_entry[key] = value

        return json.dumps(log_entry, default=str)


def _get_log_level() -> int:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _configure_logging() -> None:
    global _CONFIGURED

    base_logger = logging.getLogger(_BASE_LOGGER_NAME)
    base_logger.setLevel(_get_log_level())
    base_logger.propagate = False

    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        base_logger.handlers.clear()
        base_logger.addHandler(handler)
        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return an application logger configured for structured JSON output."""
    _configure_logging()

    logger_name = name
    if not name.startswith(_BASE_LOGGER_NAME):
        logger_name = f"{_BASE_LOGGER_NAME}.{name}"

    logger = logging.getLogger(logger_name)
    logger.setLevel(_get_log_level())
    logger.propagate = True
    return logger
