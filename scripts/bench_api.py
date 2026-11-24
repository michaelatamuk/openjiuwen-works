"""Measure read-API p95 with 20 live SSE connections.

    python scripts/bench_api.py
    python scripts/bench_api.py --tasks 200 --requests 300 --max-p95-ms 250

The 10,000-task status budget is a separate slow test; this gate exercises the HTTP read path with
many open streams, which is what the UI and a native client hold in practice.
"""

# ruff: noqa: S101 - a benchmark asserts its budget and only calls loopback URLs

from __future__ import annotations

import argparse
import http.client
import json
import shutil
import socket
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from works.adapters.queue.index import TaskIndex
from works.config.paths import WorksPaths
from works.interfaces.api.app import create_app

BASE = "/api/v1"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def wait_health(port: int, timeout: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{BASE}/health", timeout=1
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("ok"):
                return body
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    raise RuntimeError("the benchmark server did not become healthy")


def open_streams(port: int, count: int) -> list[tuple[http.client.HTTPConnection, object]]:
    opened: list[tuple[http.client.HTTPConnection, object]] = []
    for _ in range(count):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        connection.request("GET", f"{BASE}/events")
        response = connection.getresponse()
        assert response.status == 200
        connected = False
        for _ in range(10):
            line = response.readline()
            if b"connected" in line:
                connected = True
                break
        assert connected, "SSE stream did not send the connected comment"
        opened.append((connection, response))
        time.sleep(0.02)
    return opened


def close_streams(opened: list[tuple[http.client.HTTPConnection, object]]) -> None:
    for connection, _response in opened:
        connection.close()


def measure(port: int, path: str, requests: int) -> list[float]:
    for _ in range(10):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read()
    samples: list[float] = []
    for _ in range(requests):
        started = time.perf_counter()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=int, default=10000)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--streams", type=int, default=20)
    parser.add_argument("--max-p95-ms", type=float, default=250.0)
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - install hint
        raise SystemExit("install the server extra first: uv sync --extra server") from exc

    root = Path(tempfile.mkdtemp(prefix="works-bench-")) / "home"
    paths = WorksPaths(root).ensure()
    payloads = [
        {
            "id": f"t-{index:012d}",
            "state": "queued",
            "flow": "fix-issue",
            "product": "Bench",
            "repo": ".",
            "source": {
                "kind": "manual",
                "ref": f"BENCH-{index}",
                "title": f"Bench {index}",
            },
            "kind": "fix",
            "attempts": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        for index in range(args.tasks)
    ]
    TaskIndex(paths.queue / "index.sqlite3").replace(payloads)

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(paths),
            host="127.0.0.1",
            port=port,
            log_level="critical",
            log_config=None,
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, name="works-bench", daemon=True)
    thread.start()
    opened: list[tuple[http.client.HTTPConnection, object]] = []
    try:
        wait_health(port)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{BASE}/tasks?limit=200", timeout=10
        ) as response:
            response.read()
        opened = open_streams(port, args.streams)
        tasks = measure(port, f"{BASE}/tasks?limit=200", args.requests)
        health = measure(port, f"{BASE}/health", args.requests)
        result = {
            "tasks": args.tasks,
            "streams": args.streams,
            "requests": args.requests,
            "list_p50_ms": round(percentile(tasks, 0.50), 2),
            "list_p95_ms": round(percentile(tasks, 0.95), 2),
            "list_p99_ms": round(percentile(tasks, 0.99), 2),
            "health_p95_ms": round(percentile(health, 0.95), 2),
        }
        print(json.dumps(result, separators=(",", ":")))
        if result["list_p95_ms"] > args.max_p95_ms:
            print(
                f"p95 {result['list_p95_ms']} ms exceeds {args.max_p95_ms} ms",
            )
            return 1
        return 0
    finally:
        close_streams(opened)
        server.should_exit = True
        thread.join(timeout=10)
        shutil.rmtree(root.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
