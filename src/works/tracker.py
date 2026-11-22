"""Trackers: return the result to the place the signal came from.

A tracker is not a forge. GitHub/GitLab issues and Jira issues get one marker comment per run and,
on a successful confirmation, a close or a transition to Done. Every call is idempotent.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Protocol, runtime_checkable

from .errors import ConfigError
from .forge import SOURCE_ISSUE, Transport, gitlab_project, request

JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
DONE_NAMES = {"done", "closed", "resolved", "complete", "completed"}


@runtime_checkable
class Tracker(Protocol):
    name: str

    def ensure_comment(self, *, ref: str, body: str, marker: str) -> str: ...

    def close(self, *, ref: str) -> None: ...


def _github_issue(ref: str) -> tuple[str, int]:
    match = SOURCE_ISSUE.match(ref)
    if match is None:
        raise ConfigError(f"not a GitHub issue reference: {ref!r}")
    return f"{match.group('owner')}/{match.group('repo')}", int(match.group("number"))


class GitHubTracker:
    name = "github"

    def __init__(self, *, token: str | None = None, transport: Transport = request) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN")
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ConfigError("GitHub return needs GITHUB_TOKEN")
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "openjiuwen-works",
        }

    def ensure_comment(self, *, ref: str, body: str, marker: str) -> str:
        repository, number = _github_issue(ref)
        url = f"https://api.github.com/repos/{repository}/issues/{number}/comments?per_page=100"
        status, payload = self._transport(url, "GET", self._headers(), None)
        if status == 200 and isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and marker in str(item.get("body") or ""):
                    return str(item.get("html_url") or "")
        status, payload = self._transport(
            f"https://api.github.com/repos/{repository}/issues/{number}/comments",
            "POST",
            self._headers(),
            {"body": body},
        )
        if status not in (200, 201) or not isinstance(payload, dict):
            raise ConfigError(f"GitHub refused the source comment: {status} {payload}")
        return str(payload.get("html_url") or "")

    def close(self, *, ref: str) -> None:
        repository, number = _github_issue(ref)
        status, payload = self._transport(
            f"https://api.github.com/repos/{repository}/issues/{number}",
            "PATCH",
            self._headers(),
            {"state": "closed"},
        )
        if status not in (200, 201):
            raise ConfigError(f"GitHub refused to close the issue: {status} {payload}")


class GitLabTracker:
    name = "gitlab"

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        transport: Transport = request,
    ) -> None:
        self._token = token or os.environ.get("GITLAB_TOKEN")
        self._base = (base_url or os.environ.get("GITLAB_URL") or "https://gitlab.com").rstrip("/")
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ConfigError("GitLab return needs GITLAB_TOKEN")
        return {"PRIVATE-TOKEN": self._token, "User-Agent": "openjiuwen-works"}

    def _issue(self, ref: str) -> tuple[str, int]:
        return _github_issue(ref)

    def ensure_comment(self, *, ref: str, body: str, marker: str) -> str:
        repository, number = self._issue(ref)
        project = gitlab_project(repository) or repository
        encoded = _quote_project(project)
        url = f"{self._base}/api/v4/projects/{encoded}/issues/{number}/notes?per_page=100"
        status, payload = self._transport(url, "GET", self._headers(), None)
        if status == 200 and isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and marker in str(item.get("body") or ""):
                    return str(item.get("web_url") or "")
        status, payload = self._transport(
            f"{self._base}/api/v4/projects/{encoded}/issues/{number}/notes",
            "POST",
            self._headers(),
            {"body": body},
        )
        if status not in (200, 201) or not isinstance(payload, dict):
            raise ConfigError(f"GitLab refused the source note: {status} {payload}")
        return str(payload.get("web_url") or "")

    def close(self, *, ref: str) -> None:
        repository, number = self._issue(ref)
        project = gitlab_project(repository) or repository
        status, payload = self._transport(
            f"{self._base}/api/v4/projects/{_quote_project(project)}/issues/{number}",
            "PUT",
            self._headers(),
            {"state_event": "close"},
        )
        if status not in (200, 201):
            raise ConfigError(f"GitLab refused to close the issue: {status} {payload}")


def _quote_project(project: str) -> str:
    from urllib.parse import quote

    return quote(project, safe="")


class JiraTracker:
    name = "jira"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        transport: Transport = request,
    ) -> None:
        self._base = (base_url or os.environ.get("JIRA_URL") or "").rstrip("/")
        self._email = email or os.environ.get("JIRA_EMAIL")
        self._token = token or os.environ.get("JIRA_TOKEN")
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._base or not self._email or not self._token:
            raise ConfigError("Jira return needs JIRA_URL, JIRA_EMAIL and JIRA_TOKEN")
        auth = base64.b64encode(f"{self._email}:{self._token}".encode()).decode()
        return {"Authorization": f"Basic {auth}", "Accept": "application/json"}

    @staticmethod
    def _key(ref: str) -> str:
        if not JIRA_KEY.match(ref):
            raise ConfigError(f"not a Jira issue key: {ref!r}")
        return ref

    def ensure_comment(self, *, ref: str, body: str, marker: str) -> str:
        key = self._key(ref)
        url = f"{self._base}/rest/api/2/issue/{key}/comment?maxResults=100"
        status, payload = self._transport(url, "GET", self._headers(), None)
        if status == 200 and isinstance(payload, dict):
            for item in payload.get("comments") or []:
                if isinstance(item, dict) and marker in _comment_text(item.get("body")):
                    return str(item.get("self") or "")
        status, payload = self._transport(
            f"{self._base}/rest/api/2/issue/{key}/comment",
            "POST",
            self._headers(),
            {"body": body},
        )
        if status not in (200, 201) or not isinstance(payload, dict):
            raise ConfigError(f"Jira refused the source comment: {status} {payload}")
        return str(payload.get("self") or "")

    def close(self, *, ref: str) -> None:
        key = self._key(ref)
        status, payload = self._transport(
            f"{self._base}/rest/api/2/issue/{key}?fields=status",
            "GET",
            self._headers(),
            None,
        )
        if status == 200 and isinstance(payload, dict):
            name = str(((payload.get("fields") or {}).get("status") or {}).get("name") or "")
            if name.lower() in DONE_NAMES:
                return
        status, payload = self._transport(
            f"{self._base}/rest/api/2/issue/{key}/transitions",
            "GET",
            self._headers(),
            None,
        )
        if status != 200 or not isinstance(payload, dict):
            raise ConfigError(f"Jira refused the transition list: {status} {payload}")
        transitions = [
            item
            for item in payload.get("transitions") or []
            if isinstance(item, dict) and str(item.get("name") or "").lower() in DONE_NAMES
        ]
        if not transitions:
            raise ConfigError(f"Jira issue {key} has no transition to Done")
        status, payload = self._transport(
            f"{self._base}/rest/api/2/issue/{key}/transitions",
            "POST",
            self._headers(),
            {"transition": {"id": transitions[0]["id"]}},
        )
        if status not in (200, 204):
            raise ConfigError(f"Jira refused the transition: {status} {payload}")


def _comment_text(body: Any) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return json.dumps(body, ensure_ascii=False)
    return ""


def tracker_accepts(name: str, ref: str) -> bool:
    if name == "jira":
        return bool(JIRA_KEY.match(ref))
    if name in ("github", "gitlab"):
        return SOURCE_ISSUE.match(ref) is not None
    return False


def build_tracker(name: str, *, transport: Transport = request) -> Tracker | None:
    if name == "none":
        return None
    if name == "github":
        return GitHubTracker(transport=transport)
    if name == "gitlab":
        return GitLabTracker(transport=transport)
    if name == "jira":
        return JiraTracker(transport=transport)
    raise ConfigError(f"unknown tracker {name!r}; expected none, github, gitlab or jira")
