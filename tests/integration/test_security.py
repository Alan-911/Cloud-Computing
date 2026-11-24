"""Write authentication policy and security response headers."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import KEY_PREFIX, hash_key
from app.main import create_app
from tests.conftest import TEST_API_KEY

ITEMS = "/api/v1/items"


def anonymous(client: TestClient) -> TestClient:
    client.headers.pop("X-API-Key", None)
    return client


class TestWriteAuth:
    def test_reads_are_public(self, client: TestClient) -> None:
        c = anonymous(client)
        assert c.get(ITEMS).status_code == 200
        assert c.get("/api/health").status_code == 200

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", ITEMS, {"name": "x"}),
            ("PUT", f"{ITEMS}/1", {"name": "x"}),
            ("PATCH", f"{ITEMS}/1", {"name": "x"}),
            ("DELETE", f"{ITEMS}/1", None),
        ],
    )
    def test_writes_need_a_key(self, client: TestClient, method, path, body) -> None:
        r = anonymous(client).request(method, path, json=body)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"
        assert r.headers["www-authenticate"].startswith("ApiKey")

    def test_auth_is_checked_before_body_validation(self, client: TestClient) -> None:
        # An anonymous caller learns nothing about the schema.
        r = anonymous(client).post(ITEMS, json={"bogus": True})
        assert r.status_code == 401

    def test_wrong_key_rejected_and_logged_without_the_key(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="app.security"):
            r = anonymous(client).post(
                ITEMS, json={"name": "x"}, headers={"X-API-Key": "cbe_wrong_key_123456"}
            )
        assert r.status_code == 401
        assert "invalid API key" in caplog.text
        assert "cbe_wrong_key_123456" not in caplog.text

    def test_valid_key_in_header(self, client: TestClient) -> None:
        r = anonymous(client).post(
            ITEMS, json={"name": "auth-header"}, headers={"X-API-Key": TEST_API_KEY}
        )
        assert r.status_code == 201

    def test_valid_key_as_bearer_token(self, client: TestClient) -> None:
        r = anonymous(client).post(
            ITEMS, json={"name": "auth-bearer"}, headers={"Authorization": f"Bearer {TEST_API_KEY}"}
        )
        assert r.status_code == 201

    def test_any_of_several_keys_works(self, database_url: str, clean_db: None) -> None:
        settings = Settings(
            environment="test",
            database_url=database_url,
            api_key_hashes=f"{hash_key('cbe_old')}, {hash_key('cbe_new')}",
            _env_file=None,
        )
        with TestClient(create_app(settings)) as c:
            assert (
                c.post(ITEMS, json={"name": "k1"}, headers={"X-API-Key": "cbe_old"}).status_code
                == 201
            )
            assert (
                c.post(ITEMS, json={"name": "k2"}, headers={"X-API-Key": "cbe_new"}).status_code
                == 201
            )

    @pytest.mark.parametrize("environment", ["production", "staging"])
    def test_fails_closed_without_keys_outside_development(
        self, database_url: str, clean_db: None, environment: str
    ) -> None:
        settings = Settings(environment=environment, database_url=database_url, _env_file=None)
        with TestClient(create_app(settings)) as c:
            r = c.post(ITEMS, json={"name": "x"}, headers={"X-API-Key": "anything"})
            assert r.status_code == 401
            assert "no API keys are configured" in r.json()["error"]["message"]
            assert c.get(ITEMS).status_code == 200

    def test_open_in_development_without_keys(self, database_url: str, clean_db: None) -> None:
        settings = Settings(environment="development", database_url=database_url, _env_file=None)
        with TestClient(create_app(settings)) as c:
            assert c.post(ITEMS, json={"name": "dev-open"}).status_code == 201

    def test_openapi_declares_the_key_on_writes_only(self, client: TestClient) -> None:
        spec = client.get("/api/openapi.json").json()
        assert "APIKeyHeader" in spec["components"]["securitySchemes"]
        item_path = spec["paths"][f"{ITEMS}/{{item_id}}"]
        assert "security" in item_path["delete"] and "security" not in item_path["get"]
        assert "401" in spec["paths"][ITEMS]["post"]["responses"]


def test_key_format() -> None:
    assert hash_key("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert KEY_PREFIX == "cbe_"


class TestSecurityHeaders:
    EXPECTED = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cross-origin-resource-policy": "same-origin",
        "cache-control": "no-store",
    }

    @pytest.mark.parametrize("path", ["/api/health", f"{ITEMS}/999", "/metrics", "/nope"])
    def test_present_on_every_response(self, client: TestClient, path: str) -> None:
        r = client.get(path)
        for name, value in self.EXPECTED.items():
            assert r.headers.get(name) == value, (path, name)
        assert r.headers["content-security-policy"].startswith("default-src 'none'")

    def test_docs_page_is_not_blocked_by_csp(self, client: TestClient) -> None:
        r = client.get("/api/docs")
        assert r.status_code == 200
        assert "content-security-policy" not in r.headers
        assert r.headers["x-frame-options"] == "DENY"

    def test_no_server_version_disclosure(self, client: TestClient) -> None:
        assert "server" not in client.get("/api/health").headers
