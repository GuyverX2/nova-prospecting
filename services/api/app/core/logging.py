"""Structured logging with request correlation.

Logs are emitted as one JSON object per line so a platform log agent can index
them. A request id travels through a context variable, which keeps correlation
working inside services that never see the HTTP request object.

Never log credentials: bearer tokens, API keys, SMTP passwords and recipient
addresses stay out of log records by construction. Use domains or hashes.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import settings

_request_id: ContextVar[str | None] = ContextVar("nova_request_id", default=None)

MAX_REQUEST_ID_LENGTH = 200
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(value: str | None) -> str:
    """Accept an inbound correlation id without letting it poison the logs."""
    if not value:
        return new_request_id()
    cleaned = "".join(char for char in value if char.isprintable() and char not in "\r\n")
    cleaned = cleaned.strip()[:MAX_REQUEST_ID_LENGTH]
    return cleaned or new_request_id()


def set_request_id(value: str | None) -> str:
    request_id = sanitize_request_id(value)
    _request_id.set(request_id)
    return request_id


def get_request_id() -> str | None:
    return _request_id.get()


def reset_request_id() -> None:
    _request_id.set(None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "request_id":
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Install one stdout handler; idempotent so reloads do not duplicate logs."""
    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)
    # uvicorn installs its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
