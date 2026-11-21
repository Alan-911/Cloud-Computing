"""Error envelope rendering, tested on a bare app with no database."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import ConflictError, NotFoundError, error_body, register_error_handlers


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    def not_found() -> None:
        raise NotFoundError("gone", {"id": 7})

    @app.get("/conflict")
    def conflict() -> None:
        raise ConflictError("taken")

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(418, "short and stout", headers={"X-Kind": "teapot"})

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/typed/{n}")
    def typed(n: int) -> int:
        return n

    return TestClient(app, raise_server_exceptions=False)


def test_error_body_shape() -> None:
    assert error_body("c", "m") == {"error": {"code": "c", "message": "m", "details": None}}


def test_app_errors(client: TestClient) -> None:
    r = client.get("/not-found")
    assert r.status_code == 404
    assert r.json() == error_body("not_found", "gone", {"id": 7})
    r = client.get("/conflict")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_http_exception_keeps_headers_and_falls_back_to_generic_code(client: TestClient) -> None:
    r = client.get("/teapot")
    assert r.status_code == 418
    assert r.headers["x-kind"] == "teapot"
    assert r.json() == error_body("http_error", "short and stout")


def test_method_not_allowed(client: TestClient) -> None:
    r = client.post("/conflict")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


def test_validation_error_lists_fields(client: TestClient) -> None:
    r = client.get("/typed/abc")
    assert r.status_code == 422
    (detail,) = r.json()["error"]["details"]
    assert detail["field"] == "path.n" and detail["type"] == "int_parsing"


def test_unhandled_exception_hides_internals(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json() == error_body("internal_error", "An unexpected error occurred.")
    assert "secret" not in r.text
    assert "Unhandled error" in caplog.text
