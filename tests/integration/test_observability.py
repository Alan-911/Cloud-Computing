"""Request IDs, access logs and Prometheus metrics through the real app."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

ITEMS = "/api/v1/items"


def metric_value(text: str, name: str, **labels: str) -> float:
    """Value of one sample in Prometheus text format, or 0 if absent."""
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        match = re.match(r"^([a-zA-Z_:][\w:]*)(\{(.*)\})? (\S+)$", line)
        if not match or match.group(1) != name:
            continue
        found = dict(re.findall(r'(\w+)="([^"]*)"', match.group(3) or ""))
        if all(found.get(k) == v for k, v in labels.items()):
            return float(match.group(4))
    return 0.0


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def access_records():
    handler = ListHandler()
    logger = logging.getLogger("app.access")
    logger.addHandler(handler)
    yield handler.records
    logger.removeHandler(handler)


class TestRequestId:
    def test_generated_when_absent(self, client: TestClient) -> None:
        rid = client.get("/api/health/live").headers["x-request-id"]
        assert re.fullmatch(r"[0-9a-f]{32}", rid)

    def test_client_value_is_propagated(self, client: TestClient) -> None:
        r = client.get("/api/health/live", headers={"X-Request-ID": "trace-abc.123"})
        assert r.headers["x-request-id"] == "trace-abc.123"

    @pytest.mark.parametrize("bad", ["has space", "x" * 129, "semi;colon", ""])
    def test_unsafe_client_value_is_replaced(self, client: TestClient, bad: str) -> None:
        r = client.get("/api/health/live", headers={"X-Request-ID": bad})
        assert r.headers["x-request-id"] != bad
        assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])

    def test_present_on_errors(self, client: TestClient) -> None:
        r = client.get(f"{ITEMS}/999")
        assert r.status_code == 404 and "x-request-id" in r.headers


class TestAccessLog:
    def test_one_structured_line_per_request(self, client: TestClient, access_records) -> None:
        client.get(f"{ITEMS}/7", headers={"X-Request-ID": "log-check-1"})
        (record,) = [r for r in access_records if r.http_path == f"{ITEMS}/7"]
        assert record.http_route == "/api/v1/items/{item_id}"
        assert record.http_status == 404 and record.http_method == "GET"
        assert record.duration_ms >= 0
        assert record.levelno == logging.INFO

    def test_metrics_scrapes_are_not_logged(self, client: TestClient, access_records) -> None:
        client.get("/metrics")
        assert not [r for r in access_records if r.http_path == "/metrics"]


class TestMetrics:
    def test_exposed_in_prometheus_format(self, client: TestClient) -> None:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert metric_value(r.text, "app_info", environment="test") == 1.0

    def test_not_in_openapi_or_under_api_prefix(self, client: TestClient) -> None:
        assert "/metrics" not in client.get("/api/openapi.json").json()["paths"]
        assert client.get("/api/metrics").status_code == 404

    def test_counts_by_route_template_not_raw_path(self, client: TestClient) -> None:
        labels = {"method": "GET", "route": "/api/v1/items/{item_id}", "status": "404"}
        before = metric_value(client.get("/metrics").text, "http_requests_total", **labels)
        for item_id in (101, 102, 103):
            client.get(f"{ITEMS}/{item_id}")
        text = client.get("/metrics").text
        assert metric_value(text, "http_requests_total", **labels) == before + 3
        assert 'route="/api/v1/items/101"' not in text  # no per-ID series

    def test_latency_histogram_and_unmatched_routes(self, client: TestClient) -> None:
        client.post(ITEMS, json={"name": "metric-item"})
        client.get("/no/such/path")
        text = client.get("/metrics").text
        assert (
            metric_value(text, "http_request_duration_seconds_count", method="POST", route=ITEMS)
            >= 1
        )
        assert (
            metric_value(text, "http_requests_total", method="GET", route="unmatched", status="404")
            >= 1
        )

    def test_in_progress_returns_to_zero(self, client: TestClient) -> None:
        client.get("/api/health/live")
        assert metric_value(client.get("/metrics").text, "http_requests_in_progress") == 0
