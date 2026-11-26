"""Webhook intake: signed, replay-safe, rate-limited, audited.

One endpoint serves every source. The registry (`<home>/.works/sources.json`) names the secret env
var and the product a source feeds; the default entries are `github` and `generic`. A delivery is
authenticated by HMAC over the raw body, deduplicated by `X-GitHub-Delivery`/`X-Works-Delivery`, and
the resulting task is deduplicated by the signal's `dedupe_key`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.application import reporter
from works.application.intake.products import resolve_repo
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind

WINDOW_S = 60.0
MAX_DELIVERIES = 1000
SEVERITIES = ("S1", "S2", "S3", "S4")


class SourceConfig(BaseModel):
    name: str
    product: str = "openjiuwen"
    repo: str | None = None
    secret_env: str
    limit_per_minute: int = Field(default=60, gt=0)
    enabled: bool = True


DEFAULTS = {
    "github": SourceConfig(
        name="github",
        secret_env="WORKS_WEBHOOK_SECRET_GITHUB",  # noqa: S106  # nosec B106 - a variable name
        limit_per_minute=60,
    ),
    "generic": SourceConfig(
        name="generic",
        secret_env="WORKS_WEBHOOK_SECRET_GENERIC",  # noqa: S106  # nosec B106 - a variable name
        limit_per_minute=60,
    ),
}


def registry_path(paths: WorksPaths) -> Path:
    return paths.root / ".works" / "sources.json"


def load_registry(paths: WorksPaths) -> dict[str, SourceConfig]:
    path = registry_path(paths)
    entries = {name: config.model_copy() for name, config in DEFAULTS.items()}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, raw in (payload.get("sources") or {}).items():
            entries[str(name)] = SourceConfig.model_validate({"name": name, **raw})
    return entries


def save_registry(paths: WorksPaths, entries: dict[str, SourceConfig]) -> None:
    path = registry_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "sources": {name: cfg.model_dump() for name, cfg in entries.items()},
    }
    atomic_write(path, json.dumps(payload, indent=2) + "\n")


def signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _header(headers: dict[str, str], name: str) -> str | None:
    return headers.get(name.lower())


def verify(headers: dict[str, str], body: bytes, secret: str) -> bool:
    raw = _header(headers, "x-hub-signature-256") or _header(headers, "x-works-signature")
    if not raw:
        return False
    return hmac.compare_digest(raw.strip(), signature(body, secret))


_WINDOW: dict[str, deque[float]] = {}


def rate_limited(source: str, limit: int, *, now: float | None = None) -> bool:
    moment = time.monotonic() if now is None else now
    bucket = _WINDOW.setdefault(source, deque())
    while bucket and moment - bucket[0] > WINDOW_S:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(moment)
    return False


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def seen_delivery(paths: WorksPaths, delivery: str) -> bool:
    payload = _read_json(paths.state / "webhook-deliveries.json", {"deliveries": []})
    return delivery in (payload.get("deliveries") or [])


def remember_delivery(paths: WorksPaths, delivery: str) -> None:
    path = paths.state / "webhook-deliveries.json"
    payload = _read_json(path, {"deliveries": []})
    items = [str(item) for item in payload.get("deliveries") or []]
    items.append(delivery)
    atomic_write(
        path,
        json.dumps({"deliveries": items[-MAX_DELIVERIES:]}, indent=2) + "\n",
    )


def read_metrics(paths: WorksPaths) -> dict[str, Any]:
    payload = _read_json(paths.state / "webhook-metrics.json", {})
    return payload if isinstance(payload, dict) else {}


def _count(paths: WorksPaths, source: str, outcome: str) -> None:
    metrics = read_metrics(paths)
    entry = metrics.setdefault(source, {"accepted": 0, "duplicates": 0, "rejected": 0})
    entry[outcome] = int(entry.get(outcome, 0)) + 1
    entry["last_at"] = datetime.now(tz=UTC).isoformat()
    atomic_write(paths.state / "webhook-metrics.json", json.dumps(metrics, indent=2) + "\n")


def _audit(paths: WorksPaths, record: dict[str, Any]) -> None:
    path = paths.state / "webhooks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record) + "\n")


def _github_source(payload: dict[str, Any]) -> Source:
    issue = payload.get("issue")
    repository = (payload.get("repository") or {}).get("full_name")
    if not isinstance(issue, dict) or not repository:
        raise ConfigError("the github hook expects an issues event with an issue and repository")
    number = issue.get("number")
    title = str(issue.get("title") or "").strip()
    if number is None or not title:
        raise ConfigError("the github issue has no number or title")
    labels = [
        str(item.get("name"))
        for item in issue.get("labels") or []
        if isinstance(item, dict) and item.get("name")
    ]
    severity = next((label.upper() for label in labels if label.upper() in SEVERITIES), None)
    return Source(
        kind=SourceKind.TRACKER,
        ref=f"{repository}#{number}",
        title=title,
        severity=severity,
        labels=labels,
        links=[str(issue.get("html_url"))] if issue.get("html_url") else [],
        author=(issue.get("user") or {}).get("login"),
        channel="github",
        dedupe_key=f"github:{repository}#{number}",
    )


def _generic_source(payload: dict[str, Any]) -> Source:
    ref = str(payload.get("ref") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not ref or not title:
        raise ConfigError("a generic signal needs ref and title")
    try:
        kind = SourceKind(str(payload.get("kind") or "manual"))
    except ValueError as exc:
        raise ConfigError("kind must be manual, tracker or detector") from exc
    labels = [str(item) for item in payload.get("labels") or []]
    severity = str(payload.get("severity") or "").upper() or None
    if severity is not None and severity not in SEVERITIES:
        raise ConfigError("severity must be S1, S2, S3 or S4")
    return Source(
        kind=kind,
        ref=ref,
        title=title,
        severity=severity,
        labels=labels,
        links=[str(item) for item in payload.get("links") or []],
        author=str(payload.get("author") or "").strip() or None,
        channel="webhook",
        reproduction_hint=str(payload.get("reproduction_hint") or "").strip() or None,
        dedupe_key=str(payload.get("dedupe_key") or "").strip() or None,
    )


def _comment(payload: dict[str, object]) -> tuple[str, str, str, str, str, bool]:
    """(ref, url, text, author, author_kind, closed) for an issue or PR comment."""
    issue = payload.get("issue")
    comment = payload.get("comment")
    repository = payload.get("repository")
    if (
        not isinstance(issue, dict)
        or not isinstance(comment, dict)
        or not isinstance(repository, dict)
    ):
        raise ConfigError("the github hook expects an issue_comment with an issue and a comment")
    full_name = str(repository.get("full_name") or "")
    number = issue.get("number")
    if not full_name or number is None:
        raise ConfigError("the github comment has no repository or issue number")
    user = comment.get("user")
    user = user if isinstance(user, dict) else {}
    return (
        f"{full_name}#{number}",
        str(issue.get("html_url") or ""),
        str(comment.get("body") or ""),
        str(user.get("login") or "someone"),
        str(user.get("type") or "User"),
        str(issue.get("state") or "") == "closed",
    )


def handle(
    paths: WorksPaths,
    name: str,
    headers: dict[str, str],
    body: bytes,
    *,
    queue: Queue | None = None,
    now: float | None = None,
) -> tuple[int, dict[str, Any]]:
    entries = load_registry(paths)
    config = entries.get(name)
    if config is None:
        return 404, {"ok": False, "error": f"unknown source {name!r}"}
    if not config.enabled:
        return 403, {"ok": False, "error": f"source {name!r} is disabled"}
    secret = os.environ.get(config.secret_env)
    if not secret:
        return 503, {"ok": False, "error": f"{config.secret_env} is not set"}
    delivery = (
        _header(headers, "x-github-delivery") or _header(headers, "x-works-delivery") or ""
    ).strip()

    if not verify(headers, body, secret):
        _count(paths, name, "rejected")
        _audit(paths, {"source": name, "delivery": delivery, "outcome": "bad-signature"})
        return 401, {"ok": False, "error": "signature does not match"}
    if rate_limited(name, config.limit_per_minute, now=now):
        _count(paths, name, "rejected")
        _audit(paths, {"source": name, "delivery": delivery, "outcome": "rate-limited"})
        return 429, {"ok": False, "error": "too many deliveries"}
    if delivery and seen_delivery(paths, delivery):
        _count(paths, name, "duplicates")
        _audit(paths, {"source": name, "delivery": delivery, "outcome": "duplicate-delivery"})
        return 200, {"ok": True, "duplicate": True, "delivery": delivery}
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        _count(paths, name, "rejected")
        return 400, {"ok": False, "error": "body is not JSON"}
    if not isinstance(payload, dict):
        _count(paths, name, "rejected")
        return 400, {"ok": False, "error": "body must be an object"}
    if name == "github" and _header(headers, "x-github-event") == "issue_comment":
        if payload.get("action") not in (None, "created"):
            _count(paths, name, "duplicates")
            return 200, {"ok": True, "reopened": False, "reason": "not-a-new-comment"}
        try:
            ref, url, text, author, author_kind, closed = _comment(payload)
        except ConfigError as exc:
            _count(paths, name, "rejected")
            _audit(paths, {"source": name, "delivery": delivery, "outcome": f"comment: {exc}"})
            return 422, {"ok": False, "error": str(exc)}
        reply = reporter.record_reply(
            paths,
            text=text,
            author=author,
            author_kind=author_kind,
            source=name,
            event_id=delivery or None,
            ref=ref,
            url=url or None,
            closed=closed,
            queue=queue,
        )
        if delivery:
            remember_delivery(paths, delivery)
        _count(paths, name, "accepted" if reply.reopened else "duplicates")
        _audit(
            paths,
            {
                "source": name,
                "delivery": delivery,
                "outcome": f"reporter-reply: {reply.reason}",
                "task": reply.task_id,
            },
        )
        status = 202 if reply.reopened else 200
        return status, {
            "ok": True,
            "reopened": reply.reopened,
            "reason": reply.reason,
            "task": reply.task_id,
            "delivery": delivery,
        }
    try:
        source = _github_source(payload) if name == "github" else _generic_source(payload)
        product = str(payload.get("product") or config.product).strip()
        repo_raw = str(payload.get("repo") or config.repo or "").strip()
        repo = Path(repo_raw).expanduser().resolve() if repo_raw else resolve_repo(paths, product)
    except ConfigError as exc:
        _count(paths, name, "rejected")
        _audit(paths, {"source": name, "delivery": delivery, "outcome": f"config: {exc}"})
        return 422, {"ok": False, "error": str(exc)}

    task, created = (queue or Queue(paths)).submit(
        source=source,
        flow="fix-issue",
        product=product,
        repo=str(repo),
        repo_url=str(payload.get("repo_url") or "").strip() or None,
        repo_ref=str(payload.get("repo_ref") or "").strip() or None,
    )
    if delivery:
        remember_delivery(paths, delivery)
    _count(paths, name, "accepted" if created else "duplicates")
    _audit(
        paths,
        {
            "source": name,
            "delivery": delivery,
            "outcome": "task-created" if created else "task-duplicate",
            "task": task.id,
        },
    )
    return (
        202 if created else 200,
        {"ok": True, "created": created, "task": task.id, "delivery": delivery},
    )
