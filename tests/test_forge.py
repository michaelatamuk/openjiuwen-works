from __future__ import annotations

import pytest

from works.errors import ConfigError
from works.forge import (
    GitHubForge,
    GitLabForge,
    build_forge,
    gitlab_project,
    repository_slug,
)


class FakeForgeTransport:
    def __init__(self, responses: list[tuple[int, object]]) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.responses = responses

    def __call__(self, url, method, headers, payload):
        self.calls.append((url, method, payload))
        return self.responses.pop(0)


def test_gitlab_reuses_an_existing_merge_request(monkeypatch) -> None:
    transport = FakeForgeTransport(
        [(200, [{"web_url": "https://gitlab.com/o/r/-/merge_requests/1"}])]
    )
    forge = GitLabForge(token="secret", transport=transport)  # noqa: S106

    url = forge.ensure_pull_request(
        repository="o/r", head="works/t-1", base="main", title="t", body="b"
    )

    assert url == "https://gitlab.com/o/r/-/merge_requests/1"
    assert "source_branch=works%2Ft-1" in transport.calls[0][0]
    assert "o%2Fr" in transport.calls[0][0]


def test_gitlab_creates_a_merge_request() -> None:
    transport = FakeForgeTransport(
        [(200, []), (201, {"web_url": "https://gitlab.com/o/r/-/merge_requests/2"})]
    )
    forge = GitLabForge(token="secret", transport=transport)  # noqa: S106

    url = forge.ensure_pull_request(
        repository="o/r", head="works/t-1", base="main", title="t", body="b"
    )

    assert url.endswith("/merge_requests/2")
    assert transport.calls[-1][1] == "POST"
    assert transport.calls[-1][2]["source_branch"] == "works/t-1"


def test_gitlab_needs_a_token(monkeypatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    with pytest.raises(ConfigError, match="GITLAB_TOKEN"):
        GitLabForge(transport=FakeForgeTransport([])).ensure_pull_request(
            repository="o/r", head="h", base="main", title="t", body="b"
        )


def test_the_forge_factory_rejects_an_unknown_name() -> None:
    with pytest.raises(ConfigError, match="unknown forge"):
        build_forge("bitbucket")


def test_the_forge_factory_returns_none() -> None:
    assert build_forge("none") is None


def test_remote_parsing() -> None:
    assert repository_slug("https://github.com/o/r.git") == "o/r"
    assert repository_slug("git@github.com:o/r.git") == "o/r"
    assert repository_slug("https://gitlab.com/o/r.git") is None
    assert gitlab_project("https://gitlab.com/o/r.git") == "o/r"
    assert gitlab_project("git@gitlab.com:o/r.git") == "o/r"
    assert gitlab_project("https://github.com/o/r.git") is None


def test_github_refuses_a_failed_lookup() -> None:
    transport = FakeForgeTransport([(500, {"message": "boom"})])
    forge = GitHubForge(token="secret", transport=transport)  # noqa: S106

    with pytest.raises(ConfigError, match="lookup"):
        forge.ensure_pull_request(repository="o/r", head="h", base="main", title="t", body="b")
