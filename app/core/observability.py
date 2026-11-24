"""Request IDs, access logs and Prometheus metrics, in one ASGI middleware.

Metrics follow the RED method per route template (not raw path, which would
create one time series per item ID):

    http_requests_total{method, route, status}        rate and errors
    http_request_duration_seconds{method, route}      latency histogram
    http_requests_in_progress                         concurrency (saturation)
    db_pool_connections_in_use                        pool saturation
    app_info{version, environment}                    which build is running

The default registry also exports process CPU and memory (saturation) on Linux.
Metrics are served at /metrics on the app port. nginx and the Kubernetes Gateway
only route /api/, so /metrics is reachable inside the network but not from outside.
"""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_UNMATCHED = "unmatched"
_NOT_INSTRUMENTED = {"/metrics"}

access_log = logging.getLogger("app.access")

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled, by method, route template and status code.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time to handle an HTTP request, by method and route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0),
)
HTTP_IN_PROGRESS = Gauge("http_requests_in_progress", "HTTP requests currently being handled.")
DB_POOL_IN_USE = Gauge(
    "db_pool_connections_in_use", "Database connections checked out of the pool."
)
APP_INFO = Gauge(
    "app_info", "Build information; the value is always 1.", ["version", "environment"]
)


def _request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            if _VALID_REQUEST_ID.match(candidate):
                return candidate
            break
    return uuid.uuid4().hex


def _route_template(scope: Scope) -> str:
    """Full route template, e.g. /api/v1/items/{item_id}.

    With routers included under a prefix, the matched route's path_format is
    relative to its own router (/items/{item_id}). Render it with the request's
    path parameters, check the real path ends with that, and put the template back
    in place of the rendered suffix. The prefix is static, so IDs never become labels.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    if not template:
        return _UNMATCHED
    path = scope.get("path", "")
    try:
        rendered = template.format(**scope.get("path_params", {}))
    except (KeyError, IndexError, ValueError):
        return template
    if rendered and path.endswith(rendered):
        return path[: len(path) - len(rendered)] + template
    return template


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        request_id = _request_id(scope)
        token = request_id_var.set(request_id)
        instrumented = path not in _NOT_INSTRUMENTED
        status = 500  # if the app raises before responding
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        if instrumented:
            HTTP_IN_PROGRESS.inc()
        failed = False
        try:
            await self.app(scope, receive, send_with_request_id)
        except BaseException:
            # Keep the request ID set: Starlette's 500 handler runs outside this
            # middleware and logs the traceback, which should carry the same ID.
            failed = True
            raise
        finally:
            if instrumented:
                duration = time.perf_counter() - started
                route = _route_template(scope)
                method = scope.get("method", "")
                HTTP_IN_PROGRESS.dec()
                HTTP_REQUESTS.labels(method, route, str(status)).inc()
                HTTP_LATENCY.labels(method, route).observe(duration)
                access_log.log(
                    logging.ERROR if status >= 500 else logging.INFO,
                    "%s %s %s",
                    method,
                    path,
                    status,
                    extra={
                        "http_method": method,
                        "http_path": path,
                        "http_route": route,
                        "http_status": status,
                        "duration_ms": round(duration * 1000, 2),
                        "client_ip": (scope.get("client") or ("", 0))[0],
                    },
                )
            if not failed:
                request_id_var.reset(token)


def metrics_endpoint(_: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


SHED_REQUESTS = Counter(
    "http_requests_shed_total",
    "Requests rejected with 503 because the in-flight limit was reached (load shedding).",
)
_SHED_EXEMPT_SUFFIXES = ("/health", "/health/live", "/health/ready", "/metrics")


class LoadSheddingMiddleware:
    """Reject work beyond a fixed concurrency limit instead of queueing it.

    Without a limit, a process past its capacity keeps accepting requests; they queue
    without bound, every request (including ones it could have served) waits until
    clients time out, and throughput collapses. With a limit, excess requests get an
    immediate 503 + Retry-After, and admitted requests keep normal latency.

    Health checks and /metrics are exempt: failing liveness under load would restart
    a busy pod, and failing readiness would remove capacity exactly when it is needed.
    The event loop is single-threaded, so a plain counter is race-free.
    """

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit
        self.in_flight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or self.limit <= 0
            or scope.get("path", "").endswith(_SHED_EXEMPT_SUFFIXES)
        ):
            await self.app(scope, receive, send)
            return
        if self.in_flight >= self.limit:
            SHED_REQUESTS.inc()
            body = (
                b'{"error":{"code":"overloaded","message":"The service is at capacity;'
                b' retry shortly.","details":null}}'
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", b"1"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1
