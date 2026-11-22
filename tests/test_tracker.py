from __future__ import annotations

import pytest

from works.errors import ConfigError
from works.tracker import (
    GitHubTracker,
    GitLabTracker,
    JiraTracker,
    build_tracker,
    tracker_accepts,
)


class Router:
    def __init__(self, routes: list[tuple[str, str, tuple[int, object]]]) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.routes = routes

    def __call__(self, url, method, headers, payload):
        self.calls.append((url, method, payload))
        for expected_method, part, response in self.routes:
            if method == expected_method and part in url:
                return response
        return 404, {"message": f"no route for {method} {url}"}


def test_the_tracker_accepts_the_right_reference_shapes() -> None:
    assert tracker_accepts("github", "o/r#3") is True
    assert tracker_accepts("gitlab", "o/r#3") is True
    assert tracker_accepts("jira", "FIRE-3") is True
    assert tracker_accepts("jira", "o/r#3") is False
    assert tracker_accepts("github", "FIRE-3") is False
    assert tracker_accepts("none", "FIRE-3") is False


def test_github_reuses_a_marker_comment() -> None:
    transport = Router(
        [
            (
                "GET",
                "/comments",
                (200, [{"body": "old <!-- works-run: r-1 -->", "html_url": "https://x/1"}]),
            )
        ]
    )
    tracker = GitHubTracker(token="secret", transport=transport)  # noqa: S106

    url = tracker.ensure_comment(ref="o/r#3", body="new", marker="<!-- works-run: r-1 -->")

    assert url == "https://x/1"
    assert [call[1] for call in transport.calls] == ["GET"]


def test_github_creates_one_comment_and_closes() -> None:
    transport = Router(
        [
            ("GET", "/comments", (200, [])),
            ("POST", "/comments", (201, {"html_url": "https://x/2"})),
            ("PATCH", "/issues/3", (200, {"state": "closed"})),
        ]
    )
    tracker = GitHubTracker(token="secret", transport=transport)  # noqa: S106

    url = tracker.ensure_comment(ref="o/r#3", body="new", marker="m")
    tracker.close(ref="o/r#3")

    assert url == "https://x/2"
    assert [call[1] for call in transport.calls] == ["GET", "POST", "PATCH"]


def test_gitlab_creates_a_note_and_closes() -> None:
    transport = Router(
        [
            ("GET", "/notes", (200, [])),
            ("POST", "/notes", (201, {"web_url": "https://gitlab/x#note"})),
            ("PUT", "/issues/3", (200, {"state": "closed"})),
        ]
    )
    tracker = GitLabTracker(token="secret", transport=transport)  # noqa: S106

    url = tracker.ensure_comment(ref="o/r#3", body="new", marker="m")
    tracker.close(ref="o/r#3")

    assert url == "https://gitlab/x#note"
    assert [call[1] for call in transport.calls] == ["GET", "POST", "PUT"]


def test_jira_needs_all_three_settings(monkeypatch) -> None:
    for name in ("JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigError, match="JIRA_URL"):
        JiraTracker(transport=Router([])).ensure_comment(ref="FIRE-3", body="x", marker="m")


def test_jira_reuses_a_marker_comment() -> None:
    transport = Router(
        [
            (
                "GET",
                "/comment",
                (
                    200,
                    {"comments": [{"body": "old <!-- works-run: r-1 -->", "self": "https://j/1"}]},
                ),
            )
        ]
    )
    tracker = JiraTracker(
        base_url="https://jira.example",
        email="me@example.com",
        token="secret",  # noqa: S106
        transport=transport,
    )

    url = tracker.ensure_comment(ref="FIRE-3", body="new", marker="<!-- works-run: r-1 -->")

    assert url == "https://j/1"
    assert [call[1] for call in transport.calls] == ["GET"]


def test_jira_creates_a_comment() -> None:
    transport = Router(
        [
            ("GET", "/comment", (200, {"comments": []})),
            ("POST", "/comment", (201, {"self": "https://j/2"})),
        ]
    )
    tracker = JiraTracker(
        base_url="https://jira.example",
        email="me@example.com",
        token="secret",  # noqa: S106
        transport=transport,
    )

    url = tracker.ensure_comment(ref="FIRE-3", body="new", marker="m")

    assert url == "https://j/2"
    assert transport.calls[-1][2] == {"body": "new"}


def test_jira_skips_a_close_when_the_issue_is_already_done() -> None:
    transport = Router(
        [
            (
                "GET",
                "?fields=status",
                (200, {"fields": {"status": {"name": "Done"}}}),
            )
        ]
    )
    tracker = JiraTracker(
        base_url="https://jira.example",
        email="me@example.com",
        token="secret",  # noqa: S106
        transport=transport,
    )

    tracker.close(ref="FIRE-3")

    assert [call[1] for call in transport.calls] == ["GET"]


def test_jira_transitions_to_done() -> None:
    transport = Router(
        [
            ("GET", "?fields=status", (200, {"fields": {"status": {"name": "In Progress"}}})),
            (
                "GET",
                "/transitions",
                (200, {"transitions": [{"id": "31", "name": "Done"}]}),
            ),
            ("POST", "/transitions", (204, {})),
        ]
    )
    tracker = JiraTracker(
        base_url="https://jira.example",
        email="me@example.com",
        token="secret",  # noqa: S106
        transport=transport,
    )

    tracker.close(ref="FIRE-3")

    assert [call[1] for call in transport.calls] == ["GET", "GET", "POST"]
    assert transport.calls[-1][2] == {"transition": {"id": "31"}}


def test_jira_refuses_a_close_without_a_done_transition() -> None:
    transport = Router(
        [
            ("GET", "?fields=status", (200, {"fields": {"status": {"name": "Open"}}})),
            ("GET", "/transitions", (200, {"transitions": [{"id": "1", "name": "Start"}]})),
        ]
    )
    tracker = JiraTracker(
        base_url="https://jira.example",
        email="me@example.com",
        token="secret",  # noqa: S106
        transport=transport,
    )

    with pytest.raises(ConfigError, match="no transition to Done"):
        tracker.close(ref="FIRE-3")


def test_trackers_reject_the_wrong_reference() -> None:
    with pytest.raises(ConfigError, match="not a Jira"):
        JiraTracker(
            base_url="https://jira.example",
            email="me@example.com",
            token="secret",  # noqa: S106
            transport=Router([]),
        ).ensure_comment(ref="o/r#3", body="x", marker="m")


def test_the_tracker_factory() -> None:
    assert build_tracker("none") is None
    assert isinstance(build_tracker("github"), GitHubTracker)
    assert isinstance(build_tracker("gitlab"), GitLabTracker)
    assert isinstance(build_tracker("jira"), JiraTracker)
    with pytest.raises(ConfigError, match="unknown tracker"):
        build_tracker("bugzilla")
