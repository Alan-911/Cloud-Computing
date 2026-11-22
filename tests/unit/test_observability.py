"""Edge cases of the observability middleware that the HTTP tests don't reach."""

import asyncio
import logging
import types

import pytest

from app.core.logging import configure_logging, request_id_var
from app.core.observability import ObservabilityMiddleware, _route_template


def route(path_format: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(path_format=path_format, path=path_format)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ({}, "unmatched"),
        (
            {
                "route": route("/items/{item_id}"),
                "path": "/api/v1/items/5",
                "path_params": {"item_id": "5"},
            },
            "/api/v1/items/{item_id}",
        ),
        ({"route": route("/items"), "path": "/api/v1/items", "path_params": {}}, "/api/v1/items"),
        # Parameters missing from path_params: fall back to the relative template.
        ({"route": route("/items/{item_id}"), "path": "/x", "path_params": {}}, "/items/{item_id}"),
        # Rendered suffix does not match the real path: fall back as well.
        ({"route": route("/a/{v}"), "path": "/other", "path_params": {"v": "1"}}, "/a/{v}"),
    ],
)
def test_route_template(scope: dict, expected: str) -> None:
    assert _route_template(scope) == expected


def run(middleware: ObservabilityMiddleware, scope: dict) -> list[dict]:
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def test_non_http_scopes_pass_through() -> None:
    called: list[str] = []

    async def app(scope, receive, send) -> None:
        called.append(scope["type"])

    run(ObservabilityMiddleware(app), {"type": "lifespan"})
    assert called == ["lifespan"]


def test_unhandled_error_is_counted_as_500_and_keeps_request_id() -> None:
    async def app(scope, receive, send) -> None:
        raise RuntimeError("boom")

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger = logging.getLogger("app.access")
    logger.addHandler(handler)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/boom",
        "headers": [(b"x-request-id", b"err-1")],
    }
    try:
        with pytest.raises(RuntimeError):
            run(ObservabilityMiddleware(app), scope)
    finally:
        logger.removeHandler(handler)
    (record,) = records
    assert record.http_status == 500 and record.levelno == logging.ERROR


def test_text_log_format_is_selectable() -> None:
    configure_logging("INFO", "text")
    try:
        (ours,) = [h for h in logging.getLogger().handlers if getattr(h, "_app_handler", False)]
        assert "levelname" in ours.formatter._fmt
    finally:
        configure_logging("INFO", "json")
    assert request_id_var.get() in (None, "err-1")
