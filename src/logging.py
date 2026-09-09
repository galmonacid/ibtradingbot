"""Small structured-logging setup shared by command-line entry points."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line with stable core fields."""

    _standard_fields = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the package logger once, emitting structured logs to stderr."""
    logger = logging.getLogger("momentum_ml_bot")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger
