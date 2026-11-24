import json
import logging
import sys

from app.core.logging import JsonFormatter, TextFormatter, configure_logging, request_id_var


def make_record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "test", "levelname": "INFO", "msg": msg})
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_line_has_core_fields() -> None:
    entry = json.loads(JsonFormatter().format(make_record("hi %s", args=None)))
    assert entry["message"] == "hi %s"
    assert entry["level"] == "INFO" and entry["logger"] == "test"
    assert entry["timestamp"].endswith("+00:00")
    assert "request_id" not in entry


def test_json_line_carries_request_id_and_extras() -> None:
    token = request_id_var.set("req-123")
    try:
        entry = json.loads(JsonFormatter().format(make_record(http_status=201, duration_ms=3.2)))
    finally:
        request_id_var.reset(token)
    assert entry["request_id"] == "req-123"
    assert entry["http_status"] == 201 and entry["duration_ms"] == 3.2


def test_json_line_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record()
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exception"]


def test_text_format_appends_request_id() -> None:
    token = request_id_var.set("abc")
    try:
        line = TextFormatter("%(message)s").format(make_record("x"))
    finally:
        request_id_var.reset(token)
    assert line == "x [request_id=abc]"


def test_configure_logging_is_idempotent_and_keeps_foreign_handlers() -> None:
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging("WARNING", "json")
        configure_logging("INFO", "json")
        ours = [h for h in root.handlers if getattr(h, "_app_handler", False)]
        assert len(ours) == 1
        assert foreign in root.handlers
        assert root.level == logging.INFO
        assert logging.getLogger("uvicorn.access").disabled
    finally:
        root.removeHandler(foreign)
