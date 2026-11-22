"""Structured logging.

Every log line is one JSON object on stdout, so container runtimes and log
collectors can parse it without regexes. The current request's ID is attached to
every line logged while that request is being handled, which ties the access log,
application logs and error tracebacks for one request together.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra=` and is emitted.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable format for local development (APP_LOG_FORMAT=text)."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = request_id_var.get()
        return f"{base} [request_id={request_id}]" if request_id else base


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    # Replace only the handler this function installed before (calling it twice must
    # not duplicate lines); leave handlers added by others, e.g. pytest's caplog.
    handler._app_handler = True  # type: ignore[attr-defined]
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, "_app_handler", False)]
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Route uvicorn's own loggers through the same handler. Its access log is
    # replaced by app.access (written by the observability middleware).
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
