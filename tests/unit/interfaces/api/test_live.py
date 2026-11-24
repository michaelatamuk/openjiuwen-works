from __future__ import annotations

import json
import queue as thread_queue
import time
from itertools import islice

import pytest
from fastapi.testclient import TestClient

from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind
from works.interfaces.api.app import create_app
from works.interfaces.api.live import EventHub

BASE = "http://127.0.0.1"


def test_hub_replays_and_reports_a_gap(paths) -> None:
    hub = EventHub(paths, ring=4)
    first = hub.publish("task.changed", {"task_id": "t-1"})
    second = hub.publish("job.changed", {"job_id": "j-1", "status": "running"})

    missed, gap = hub.events_after(0)
    assert gap is False
    assert [item.id for item in missed] == [first.id, second.id]
    assert hub.events_after(second.id) == ([], False)

    for _ in range(6):
        hub.publish("queue.changed", {})
    missed, gap = hub.events_after(0)
    assert gap is True
    assert missed == []


def test_a_subscriber_receives_published_events(paths) -> None:
    hub = EventHub(paths)
    channel = hub.subscribe()
    try:
        item = hub.publish("task.changed", {"task_id": "t-2"})
        received = channel.get(timeout=1)
        assert received == item
    finally:
        hub.unsubscribe(channel)


def test_live_state_maps_task_and_job_changes(paths) -> None:
    hub = EventHub(paths)
    channel = hub.subscribe()
    hub.start()
    try:
        task_dir = paths.queue / "t-demo"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(json.dumps({"id": "t-demo"}), encoding="utf-8")
        (paths.state / "jobs").mkdir(parents=True, exist_ok=True)
        (paths.state / "jobs" / "j-demo.json").write_text(
            json.dumps({"id": "j-demo", "status": "running"}), encoding="utf-8"
        )
        seen: dict[str, dict[str, object]] = {}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len(seen) < 2:
            try:
                item = channel.get(timeout=0.2)
            except thread_queue.Empty:
                continue
            seen[item.event] = item.data
        assert seen["task.changed"] == {"task_id": "t-demo"}
        assert seen["job.changed"] == {"job_id": "j-demo", "status": "running"}
    finally:
        hub.stop()
        hub.unsubscribe(channel)


def test_the_sse_route_sends_a_connected_comment(paths) -> None:
    app = create_app(paths)
    with (
        TestClient(app, base_url=BASE) as client,
        client.stream("GET", "/api/v1/events") as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.iter_lines()
        assert next(lines) == ": connected"


def test_the_sse_route_resyncs_when_the_ring_is_behind(paths) -> None:
    app = create_app(paths, writable=False)
    with TestClient(app, base_url=BASE) as client:
        hub = app.state.works.live
        for _ in range(260):
            hub.publish("queue.changed", {})
        with client.stream("GET", "/api/v1/events", headers={"Last-Event-ID": "1"}) as response:
            lines = response.iter_lines()
            assert next(lines) == ": connected"
            payload = [line for line in islice(lines, 6) if line]
        assert "event: resync" in payload
        assert any('"reason": "gap"' in line for line in payload), payload


def test_ask_stream_forwards_events(paths, monkeypatch) -> None:
    queue = Queue(paths)
    task, _ = queue.submit(
        source=Source(kind=SourceKind.MANUAL, ref="ASK-1", title="ask"),
        flow="fix-issue",
        product="Fixture",
        repo=".",
    )

    def fake_stream(_paths, _task_id, _question):
        yield {"type": "delta", "text": "hi"}
        yield {"type": "done", "text": "hi", "recorded": True}

    import works.application.assistant.chat as chat

    monkeypatch.setattr(chat, "ask_mira_stream", fake_stream)
    app = create_app(paths, writable=True)
    with TestClient(app, base_url=BASE) as client:
        token = app.state.works.security.token
        response = client.post(
            "/api/v1/ask/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"task_id": task.id, "question": "why?"},
        )
    assert response.status_code == 200
    assert '"type": "delta"' in response.text
    assert '"type": "done"' in response.text


def test_twenty_subscribers_receive_the_same_event(paths) -> None:
    hub = EventHub(paths)
    channels = [hub.subscribe() for _ in range(20)]
    try:
        event = hub.publish("queue.changed", {"reason": "load"})
        assert event.id == 1
        for channel in channels:
            received = channel.get_nowait()
            assert received.id == event.id
            assert received.event == "queue.changed"
    finally:
        for channel in channels:
            hub.unsubscribe(channel)


def test_the_event_hub_caps_subscribers(paths) -> None:
    from works.domain.errors import UnavailableError

    hub = EventHub(paths, max_subscribers=2)
    first = hub.subscribe()
    second = hub.subscribe()
    with pytest.raises(UnavailableError):
        hub.subscribe()
    hub.unsubscribe(first)
    hub.unsubscribe(second)
