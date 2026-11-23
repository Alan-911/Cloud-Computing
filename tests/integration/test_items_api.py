"""End-to-end checks of every public endpoint through the HTTP layer.
Phase 03 expands this into a full suite against PostgreSQL."""

from fastapi.testclient import TestClient

ITEMS = "/api/v1/items"


def create(client: TestClient, name: str, description: str | None = None) -> dict:
    r = client.post(ITEMS, json={"name": name, "description": description})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "version": client.app.version,
        "environment": "test",
        "database": "ok",
    }


def test_crud_round_trip(client: TestClient) -> None:
    item = create(client, "  alpha  ", "first")
    assert item["name"] == "alpha"
    assert item["created_at"].endswith(("Z", "+00:00"))

    r = client.get(f"{ITEMS}/{item['id']}")
    assert r.status_code == 200 and r.json()["description"] == "first"

    r = client.patch(f"{ITEMS}/{item['id']}", json={"description": "patched"})
    assert r.status_code == 200
    assert r.json()["name"] == "alpha" and r.json()["description"] == "patched"

    r = client.put(f"{ITEMS}/{item['id']}", json={"name": "beta"})
    assert r.status_code == 200
    assert r.json()["name"] == "beta" and r.json()["description"] is None

    # Perform the request outside the assert: under `python -O`, asserts (and any
    # side effects inside them) are stripped.
    deleted = client.delete(f"{ITEMS}/{item['id']}")
    assert deleted.status_code == 204
    assert client.get(f"{ITEMS}/{item['id']}").status_code == 404


def test_create_sets_location(client: TestClient) -> None:
    r = client.post(ITEMS, json={"name": "loc"})
    assert r.headers["location"] == f"{ITEMS}/{r.json()['id']}"


def test_pagination(client: TestClient) -> None:
    for i in range(5):
        create(client, f"item-{i}")
    r = client.get(ITEMS, params={"limit": 2, "offset": 2})
    body = r.json()
    assert body["total"] == 5 and body["limit"] == 2 and body["offset"] == 2
    assert [i["name"] for i in body["items"]] == ["item-2", "item-3"]


def test_page_size_capped(client: TestClient) -> None:
    assert client.get(ITEMS, params={"limit": 1000}).json()["limit"] == 100
    assert client.get(ITEMS).json()["limit"] == 20


def test_duplicate_name_conflict_is_case_insensitive(client: TestClient) -> None:
    create(client, "Alpha")
    r = client.post(ITEMS, json={"name": "alpha"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_rename_into_existing_name_conflicts(client: TestClient) -> None:
    create(client, "one")
    two = create(client, "two")
    r = client.patch(f"{ITEMS}/{two['id']}", json={"name": "ONE"})
    assert r.status_code == 409
    assert client.get(f"{ITEMS}/{two['id']}").json()["name"] == "two"


def test_not_found_envelope(client: TestClient) -> None:
    r = client.get(f"{ITEMS}/999")
    assert r.status_code == 404
    assert r.json() == {
        "error": {"code": "not_found", "message": "Item 999 was not found.", "details": {"id": 999}}
    }


def test_validation_errors(client: TestClient) -> None:
    cases = [
        client.post(ITEMS, json={"name": "   "}),
        client.post(ITEMS, json={"name": "x" * 101}),
        client.post(ITEMS, json={"name": "ok", "extra": 1}),
        client.patch(f"{ITEMS}/1", json={}),
        client.patch(f"{ITEMS}/1", json={"name": None}),
        client.get(ITEMS, params={"limit": 0}),
        client.get(f"{ITEMS}/0"),
    ]
    for r in cases:
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == "validation_error" and err["details"]


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_openapi_documents_every_endpoint(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths) == {"/api/health", "/api/health/live", ITEMS, f"{ITEMS}/{{item_id}}"}
    assert set(paths[f"{ITEMS}/{{item_id}}"]) == {"get", "put", "patch", "delete"}
    for ops in paths.values():
        for op in ops.values():
            assert op.get("summary")


def test_liveness_does_not_need_database(client: TestClient) -> None:
    client.app.state.db.ping = lambda: False
    assert client.get("/api/health/live").json() == {"status": "ok"}
    r = client.get("/api/health/ready")
    assert r.status_code == 503 and r.json()["database"] == "unavailable"
