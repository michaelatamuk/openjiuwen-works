"""Code forges: GitHub and GitLab behind one small pull-request contract.

A forge owns branches and pull/merge requests. A tracker owns the source issue. They are separate
on purpose: a Jira issue can be returned to while the code lives on GitHub or GitLab.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from works.domain.errors import ConfigError

Transport = Callable[[str, str, dict[str, str] | None, dict[str, Any] | None], tuple[int, Any]]

SOURCE_ISSUE = re.compile(r"^(?P<owner>.+)/(?P<repo>[^/#]+)#(?P<number>\d+)$")
GITHUB_REMOTE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)")
GITLAB_REMOTE = re.compile(r"(?P<host>gitlab[^/:]*)[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)")


@runtime_checkable
class Forge(Protocol):
    name: str

    def ensure_pull_request(
        self, *, repository: str, head: str, base: str, title: str, body: str
    ) -> str: ...


def request(
    url: str,
    method: str,
    headers: dict[str, str] | None,
    payload: dict[str, Any] | None,
) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(  # noqa: S310  # nosec B310
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310  # nosec B310
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed


def repository_slug(remote: str) -> str | None:
    match = GITHUB_REMOTE.search(remote)
    if match is None:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


def gitlab_project(remote: str) -> str | None:
    match = GITLAB_REMOTE.search(remote)
    if match is None:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


class GitHubForge:
    """The smallest real GitHub surface delivery needs, behind an injectable transport."""

    name = "github"

    def __init__(self, *, token: str | None = None, transport: Transport = request) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN")
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise ConfigError("GitHub delivery needs GITHUB_TOKEN")
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "openjiuwen-works",
        }

    def ensure_pull_request(
        self, *, repository: str, head: str, base: str, title: str, body: str
    ) -> str:
        owner = repository.split("/")[0]
        url = (
            f"https://api.github.com/repos/{repository}/pulls"
            f"?state=all&head={urllib.parse.quote(f'{owner}:{head}')}"
        )
        status, payload = self._transport(url, "GET", self._headers(), None)
        if status != 200:
            raise ConfigError(f"GitHub refused the pull-request lookup: {status} {payload}")
        if isinstance(payload, list) and payload:
            existing = payload[0]
            if isinstance(existing, dict) and existing.get("html_url"):
                return str(existing["html_url"])
        status, payload = self._transport(
            f"https://api.github.com/repos/{repository}/pulls",
            "POST",
            self._headers(),
            {"title": title, "head": head, "base": base, "body": body},
        )
        if status not in (200, 201) or not isinstance(payload, dict) or not payload.get("html_url"):
            raise ConfigError(f"GitHub refused the pull request: {status} {payload}")
        return str(payload["html_url"])


class GitLabForge:
    """GitLab merge requests, self-hosted or gitlab.com."""

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
            raise ConfigError("GitLab delivery needs GITLAB_TOKEN")
        return {"PRIVATE-TOKEN": self._token, "User-Agent": "openjiuwen-works"}

    def _project(self, repository: str) -> str:
        return urllib.parse.quote(repository, safe="")

    def ensure_pull_request(
        self, *, repository: str, head: str, base: str, title: str, body: str
    ) -> str:
        project = self._project(repository)
        query = urllib.parse.urlencode({"state": "all", "source_branch": head})
        status, payload = self._transport(
            f"{self._base}/api/v4/projects/{project}/merge_requests?{query}",
            "GET",
            self._headers(),
            None,
        )
        if status != 200:
            raise ConfigError(f"GitLab refused the merge-request lookup: {status} {payload}")
        if isinstance(payload, list) and payload:
            existing = payload[0]
            if isinstance(existing, dict) and existing.get("web_url"):
                return str(existing["web_url"])
        status, payload = self._transport(
            f"{self._base}/api/v4/projects/{project}/merge_requests",
            "POST",
            self._headers(),
            {
                "source_branch": head,
                "target_branch": base,
                "title": title,
                "description": body,
            },
        )
        if status not in (200, 201) or not isinstance(payload, dict) or not payload.get("web_url"):
            raise ConfigError(f"GitLab refused the merge request: {status} {payload}")
        return str(payload["web_url"])


def build_forge(name: str, *, transport: Transport = request) -> Forge | None:
    if name == "none":
        return None
    if name == "github":
        return GitHubForge(transport=transport)
    if name == "gitlab":
        return GitLabForge(transport=transport)
    raise ConfigError(f"unknown forge {name!r}; expected none, github or gitlab")
