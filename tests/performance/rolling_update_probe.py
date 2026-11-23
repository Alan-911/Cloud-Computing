"""Continuous traffic probe for zero-downtime checks.

Sends a steady mix of reads and writes from several threads until stopped (or
for a fixed duration) and counts every request that did not succeed: non-2xx
responses, connection errors and timeouts. Exit code 1 if any request failed.

    python tests/performance/rolling_update_probe.py --url http://127.0.0.1:8088 \
        --duration 120 --workers 4

Use 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first and
adds about 2 s to every request.

Run it while a rollout happens (see scripts/k8s-rolling-update.sh). Uses only the
standard library so it runs anywhere Python does.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid


def request(method: str, url: str, body: dict | None, timeout: float, api_key: str = "") -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if api_key and method != "GET":
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def worker(
    base: str,
    stop: threading.Event,
    stats: dict,
    lock: threading.Lock,
    timeout: float,
    api_key: str = "",
):
    api = base.rstrip("/") + "/api"
    i = 0
    while not stop.is_set():
        i += 1
        if i % 4 == 0:
            op, method, url, body = (
                "create",
                "POST",
                f"{api}/v1/items",
                {"name": f"probe-{uuid.uuid4().hex[:12]}"},
            )
        elif i % 4 == 1:
            op, method, url, body = "health", "GET", f"{api}/health", None
        else:
            op, method, url, body = "list", "GET", f"{api}/v1/items?limit=5", None
        started = time.perf_counter()
        try:
            status = request(method, url, body, timeout, api_key)
            ok = 200 <= status < 300
            outcome = str(status)
        except Exception as exc:  # connection reset, refused, timeout
            ok = False
            outcome = type(exc).__name__
        elapsed_ms = (time.perf_counter() - started) * 1000
        with lock:
            stats["total"] += 1
            stats["by_op"][op] += 1
            stats["outcomes"][outcome] += 1
            stats["latencies"].append(elapsed_ms)
            if not ok:
                stats["failed"] += 1
                if len(stats["failures"]) < 20:
                    stats["failures"].append(
                        {"t": round(time.time() - stats["start"], 2), "op": op, "outcome": outcome}
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8088")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--stop-file", help="stop early when this file exists")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY", ""),
        help="key for write requests (default: $API_KEY)",
    )
    args = parser.parse_args()

    stats = {
        "start": time.time(),
        "total": 0,
        "failed": 0,
        "by_op": collections.Counter(),
        "outcomes": collections.Counter(),
        "latencies": [],
        "failures": [],
    }
    lock = threading.Lock()
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=worker,
            args=(args.url, stop, stats, lock, args.timeout, args.api_key),
            daemon=True,
        )
        for _ in range(args.workers)
    ]
    for t in threads:
        t.start()

    deadline = time.time() + args.duration
    while time.time() < deadline:
        if args.stop_file:
            try:
                open(args.stop_file).close()
                break
            except OSError:
                pass
        time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(timeout=args.timeout + 1)

    lat = sorted(stats["latencies"]) or [0.0]
    pct = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 1)  # noqa: E731
    summary = {
        "url": args.url,
        "seconds": round(time.time() - stats["start"], 1),
        "requests": stats["total"],
        "failed": stats["failed"],
        "success_rate": round(100 * (stats["total"] - stats["failed"]) / max(stats["total"], 1), 3),
        "by_operation": dict(stats["by_op"]),
        "outcomes": dict(stats["outcomes"]),
        "latency_ms": {
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "max": round(lat[-1], 1),
        },
        "first_failures": stats["failures"],
    }
    print(json.dumps(summary, indent=2))
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
