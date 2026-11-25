from __future__ import annotations

import json

import pytest

from works.adapters.queue.store import Queue
from works.application import webhooks


@pytest.fixture(autouse=True)
def _clean_window() -> None:
    webhooks._WINDOW.clear()


@pytest.fixture(autouse=True)
def _configured(paths, repo) -> None:
    entries = webhooks.load_registry(paths)
    for name in entries:
        entries[name].repo = str(repo.path)
    webhooks.save_registry(paths, entries)


def _github_body() -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "repository": {"full_name": "o/r"},
            "issue": {
                "number": 7,
                "title": "add subtracts",
                "html_url": "https://github.com/o/r/issues/7",
                "user": {"login": "michael"},
                "labels": [{"name": "S2"}, {"name": "bug"}],
            },
        }
    ).encode()


def _headers(body: bytes, secret: str, delivery: str = "d-1") -> dict[str, str]:
    return {
        "x-hub-signature-256": webhooks.signature(body, secret),
        "x-github-delivery": delivery,
        "x-github-event": "issues",
    }


def test_a_signed_delivery_creates_one_task(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GITHUB", "s3cret")
    body = _github_body()

    status, payload = webhooks.handle(paths, "github", _headers(body, "s3cret"), body)

    assert status == 202
    assert payload["created"] is True
    task = Queue(paths).load(payload["task"])
    assert task.source.ref == "o/r#7"
    assert task.source.severity == "S2"
    assert task.source.labels == ["S2", "bug"]
    assert task.source.channel == "github"
    assert task.source.dedupe_key == "github:o/r#7"


def test_the_same_delivery_is_not_applied_twice(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GITHUB", "s3cret")
    body = _github_body()
    headers = _headers(body, "s3cret")

    webhooks.handle(paths, "github", headers, body)
    status, payload = webhooks.handle(paths, "github", headers, body)

    assert status == 200
    assert payload["duplicate"] is True
    assert len(Queue(paths).list_tasks()) == 1


def test_a_bad_signature_is_rejected(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GITHUB", "s3cret")
    body = _github_body()

    status, payload = webhooks.handle(paths, "github", {"x-hub-signature-256": "sha256=bad"}, body)

    assert status == 401
    assert payload["ok"] is False
    assert Queue(paths).list_tasks() == []


def test_a_missing_secret_is_a_configuration_error(paths, repo, monkeypatch) -> None:
    monkeypatch.delenv("WORKS_WEBHOOK_SECRET_GITHUB", raising=False)

    status, _ = webhooks.handle(paths, "github", {}, _github_body())

    assert status == 503


def test_the_rate_limit_returns_retry_later(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GITHUB", "s3cret")
    body = _github_body()
    headers = _headers(body, "s3cret")
    entries = webhooks.load_registry(paths)
    entries["github"].limit_per_minute = 2
    webhooks.save_registry(paths, entries)

    codes = [
        webhooks.handle(paths, "github", headers, body, now=1000.0 + index)[0] for index in range(3)
    ]

    assert codes[:2] == [202, 200]
    assert codes[2] == 429


def test_a_disabled_source_is_refused(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GITHUB", "s3cret")
    entries = webhooks.load_registry(paths)
    entries["github"].enabled = False
    webhooks.save_registry(paths, entries)

    status, _ = webhooks.handle(paths, "github", {}, _github_body())

    assert status == 403


def test_a_generic_signal_is_accepted(paths, repo, monkeypatch) -> None:
    monkeypatch.setenv("WORKS_WEBHOOK_SECRET_GENERIC", "s3cret")
    body = json.dumps(
        {
            "ref": "MON-1",
            "title": "monitoring noticed a drop",
            "reproduction_hint": "curl -s localhost/health",
            "labels": ["monitoring"],
        }
    ).encode()
    headers = {"x-works-signature": webhooks.signature(body, "s3cret")}

    status, payload = webhooks.handle(paths, "generic", headers, body)

    assert status == 202
    task = Queue(paths).load(payload["task"])
    assert task.source.reproduction_hint == "curl -s localhost/health"
    assert task.source.kind.value == "manual"
