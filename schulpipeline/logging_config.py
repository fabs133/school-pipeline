"""Structured logging with JSON formatter and correlation IDs."""

from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Thread-local storage for correlation context
_context = threading.local()


def get_run_id() -> str:
    """Get the current run correlation ID."""
    return getattr(_context, "run_id", "")


def set_run_id(run_id: str | None = None) -> str:
    """Set the run correlation ID. Generates one if not provided."""
    rid = run_id or uuid.uuid4().hex[:12]
    _context.run_id = rid
    return rid


def get_stage() -> str:
    """Get the current stage name."""
    return getattr(_context, "stage", "")


def set_stage(stage: str) -> None:
    """Set the current stage name for log context."""
    _context.stage = stage


class JsonFormatter(logging.Formatter):
    """Outputs log records as single-line JSON for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add correlation context
        run_id = get_run_id()
        if run_id:
            entry["run_id"] = run_id

        stage = get_stage()
        if stage:
            entry["stage"] = stage

        # Add extra fields from LogRecord
        for key in ("backend", "tokens_in", "tokens_out", "cost_usd",
                     "latency_ms", "model", "elapsed_ms"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
            entry["error_type"] = type(record.exc_info[1]).__name__

        return json.dumps(entry, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Human-readable format with optional run_id prefix."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        run_id = get_run_id()
        if run_id:
            record.msg = f"[{run_id}] {record.msg}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    json_logs: bool = False,
) -> None:
    """Configure logging with optional JSON format and file output.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        log_file: Path to log file. JSON format is always used for files.
        json_logs: Use JSON format for stderr output too.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root.handlers.clear()

    # Stderr handler — human-readable by default, JSON if requested
    stderr_handler = logging.StreamHandler(sys.stderr)
    if json_logs:
        stderr_handler.setFormatter(JsonFormatter())
    else:
        stderr_handler.setFormatter(HumanFormatter())
    root.addHandler(stderr_handler)

    # File handler — always JSON for machine parsing, with rotation
    if log_file:
        from logging.handlers import RotatingFileHandler

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
