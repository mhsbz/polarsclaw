"""Structured logging setup for PolarsClaw."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(
    *,
    level: str = "INFO",
    json_output: bool = False,
    console: Console | None = None,
) -> None:
    """Configure the root logger for PolarsClaw.

    Parameters
    ----------
    level:
        Minimum log level (e.g. ``"DEBUG"``, ``"INFO"``).
    json_output:
        If ``True``, emit structured JSON lines to *stderr* instead of
        human-friendly Rich output.
    console:
        Optional :class:`rich.console.Console` to use for the Rich handler.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove any pre-existing handlers to avoid duplicate output.
    root.handlers.clear()

    if json_output:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JSONFormatter())
    else:
        handler = RichHandler(  # type: ignore[assignment]
            console=console or Console(stderr=True),
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            markup=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

    root.addHandler(handler)

    # Quieten noisy third-party loggers.
    for name in ("httpx", "httpcore", "aiosqlite", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
