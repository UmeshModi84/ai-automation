"""
Structured JSON logging for AI DevOps scripts (one JSON object per line on stdout).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONLineFormatter(logging.Formatter):
    """Emit log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "structured", None)
        if extra is None and hasattr(record, "__dict__"):
            extra = record.__dict__.get("structured")
        if isinstance(extra, dict):
            payload["data"] = extra
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that writes JSON lines to stdout (for CI log aggregation).
    Idempotent if already configured for this name's parent chain.
    """
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JSONLineFormatter())
        log.addHandler(h)
    log.propagate = False
    return log


def log_json(logger: logging.Logger, message: str, **data: Any) -> None:
    """Log with arbitrary structured fields under key ``data``."""
    logger.info(message, extra={"structured": data})
