"""Tracker intake adapters: GitHub Issues and Jira become ordinary queued tasks."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from works.adapters.queue.store import Queue
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind, Task

Transport = Callable[[str, dict[str, str]], tuple[int, Any]]


@dataclass(frozen=True)
class Issue:
    ref: str
    title: str
    body: str = ""


def _urllib_get(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310  # nosec B310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else {}


def github_issues(
    repository: str,
    *,
    label: str | None = None,
    limit: int = 20,
    token: str | None = None,
    transport: Transport = _urllib_get,
) -> list[Issue]:
    url = f"https://api.github.com/repos/{repository}/issues?state=open&per_page={limit}"
    if label:
        url += f"&labels={label}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "openjiuwen-works"}
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, payload = transport(url, headers)
    if status != 200 or not isinstance(payload, list):
        raise ConfigError(f"GitHub refused issue intake: {status} {payload}")
    issues: list[Issue] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        number = item.get("number")
        title = str(item.get("title") or "").strip()
        if number is None or not title:
            continue
        issues.append(
            Issue(
                ref=f"{repository}#{number}",
                title=title,
                body=str(item.get("body") or ""),
            )
        )
    return issues[:limit]


def jira_issues(
    base_url: str,
    jql: str,
    *,
    limit: int = 20,
    email: str | None = None,
    token: str | None = None,
    transport: Transport = _urllib_get,
) -> list[Issue]:
    email = email or os.environ.get("JIRA_EMAIL")
    token = token or os.environ.get("JIRA_TOKEN")
    if not email or not token:
        raise ConfigError("Jira intake needs JIRA_EMAIL and JIRA_TOKEN")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    url = (
        f"{base_url.rstrip('/')}/rest/api/3/search?jql={urllib.parse.quote(jql)}&maxResults={limit}"
    )
    status, payload = transport(
        url, {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    )
    if status != 200 or not isinstance(payload, dict):
        raise ConfigError(f"Jira refused issue intake: {status} {payload}")
    issues: list[Issue] = []
    for item in payload.get("issues") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        fields = item.get("fields") or {}
        title = str(fields.get("summary") or "").strip()
        if not key or not title:
            continue
        issues.append(Issue(ref=str(key), title=title))
    return issues[:limit]


def ingest_issues(
    queue: Queue, *, product: str, repo: str, issues: list[Issue]
) -> list[tuple[Task, bool]]:
    created: list[tuple[Task, bool]] = []
    for issue in issues:
        task, was_created = queue.submit(
            source=Source(kind=SourceKind.TRACKER, ref=issue.ref, title=issue.title),
            flow="fix-issue",
            product=product,
            repo=repo,
        )
        created.append((task, was_created))
    return created
