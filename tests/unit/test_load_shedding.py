"""Load shedding: excess concurrent requests get a fast 503, never a queue."""

import asyncio

import pytest

from app.core.observability import SHED_REQUESTS, LoadSheddingMiddleware


def make_app(gate: asyncio.Event, entered: list[str]):
    async def app(scope, receive, send) -> None:
        entered.append(scope["path"])
        await gate.wait()  # hold the request "in flight"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


async def call(mw, path: str) -> tuple[int, dict[bytes, bytes]]:
    status, headers = 0, {}

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        nonlocal status, headers
        if message["type"] == "http.response.start":
            status = message["status"]
            headers = dict(message["headers"])

    await mw({"type": "http", "path": path, "method": "GET", "headers": []}, receive, send)
    return status, headers


def test_requests_beyond_the_limit_are_shed_immediately() -> None:
    async def scenario() -> None:
        gate, entered = asyncio.Event(), []
        mw = LoadSheddingMiddleware(make_app(gate, entered), limit=2)
        before = SHED_REQUESTS._value.get()
        held = [asyncio.create_task(call(mw, "/api/v1/items")) for _ in range(2)]
        await asyncio.sleep(0)  # let both enter
        assert mw.in_flight == 2

        # Third request: rejected without waiting for the others.
        status, headers = await asyncio.wait_for(call(mw, "/api/v1/items"), timeout=1)
        assert status == 503
        assert headers[b"retry-after"] == b"1"
        assert SHED_REQUESTS._value.get() == before + 1

        gate.set()
        assert [s for s, _ in await asyncio.gather(*held)] == [200, 200]
        assert mw.in_flight == 0  # capacity is released

        # After release, new work is admitted again.
        assert (await call(mw, "/api/v1/items"))[0] == 200

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "path", ["/api/health", "/api/health/live", "/api/health/ready", "/metrics"]
)
def test_health_and_metrics_are_never_shed(path: str) -> None:
    async def scenario() -> None:
        gate, entered = asyncio.Event(), []
        mw = LoadSheddingMiddleware(make_app(gate, entered), limit=1)
        held = asyncio.create_task(call(mw, "/api/v1/items"))
        await asyncio.sleep(0)
        gate.set()  # exempt path is served even though the limit is reached
        assert (await call(mw, path))[0] == 200
        await held

    asyncio.run(scenario())


def test_limit_zero_disables_shedding() -> None:
    async def scenario() -> None:
        gate, entered = asyncio.Event(), []
        gate.set()
        mw = LoadSheddingMiddleware(make_app(gate, entered), limit=0)
        results = await asyncio.gather(*(call(mw, "/api/v1/items") for _ in range(20)))
        assert {s for s, _ in results} == {200}

    asyncio.run(scenario())


def test_shed_response_goes_through_the_full_app(client) -> None:
    """In the real app, shed 503s still carry security headers and a request ID."""
    from app.core.observability import LoadSheddingMiddleware as LSM

    # Find the shedding layer in the built stack and force it to "full".
    app = client.app
    app.build_middleware_stack()
    layer = app.middleware_stack
    while layer is not None and not isinstance(layer, LSM):
        layer = getattr(layer, "app", None)
    assert layer is not None, "LoadSheddingMiddleware not installed"
    original = layer.limit
    layer.in_flight = layer.limit = 1
    try:
        r = client.get("/api/v1/items")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "overloaded"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "x-request-id" in r.headers
        assert client.get("/api/health/live").status_code == 200
    finally:
        layer.in_flight, layer.limit = 0, original
