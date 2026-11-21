from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from works.flow import PathsSpec
from works.policy import (
    check_patch,
    check_paths,
    is_unsafe,
    normalize_path,
    paths_from_patch,
)

DENIED = [
    "tests/test_core.py",
    "pkg/tests/test_core.py",
    "conftest.py",
    "pkg/conftest.py",
    "pytest.ini",
    "tox.ini",
    "migrations/001_init.py",
    "scenarios/fix-add.yaml",
    ".github/workflows/ci.yml",
    "pkg/.github/workflows/release.yml",
    "quarantine.json",
    "TESTS/test_core.py",
    "Tests/helpers.py",
    "tests./test_core.py",
    "test_core.py",
    "pkg/test_core.py",
    "core_test.py",
]

ALLOWED = [
    "calc/core.py",
    "src/works/queue.py",
    "README.md",
    "docs/design/notes.md",
    "calculations/tests_data.py",
]


@pytest.mark.parametrize("path", DENIED)
def test_default_deny(path: str) -> None:
    violations = check_paths([path], PathsSpec())
    assert violations, f"{path} should be denied"


@pytest.mark.parametrize("path", ALLOWED)
def test_default_allow(path: str) -> None:
    assert check_paths([path], PathsSpec()) == []


@pytest.mark.parametrize(
    "path",
    [
        "../calc/core.py",
        "calc/../../etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\x",
        "\\\\share\\x",
        "~/.ssh/id_rsa",
        "",
    ],
)
def test_unsafe_paths_are_refused(path: str) -> None:
    assert is_unsafe(path)
    assert check_paths([path], PathsSpec())


def test_normalisation_removes_dot_segments_and_separators() -> None:
    assert normalize_path(".\\calc//./core.py") == "calc/core.py"
    assert normalize_path("a/b/../c") == "a/b/../c"
    assert normalize_path("tests. /x.py") == "tests/x.py"


def test_a_leading_dot_slash_is_normalised_not_refused() -> None:
    assert check_paths(["./calc/core.py"], PathsSpec()) == []
    assert check_paths(["./tests/test_core.py"], PathsSpec())


def test_quoted_diff_paths_are_unquoted_before_the_check() -> None:
    patch = (
        'diff --git "a/tests/test x.py" "b/tests/test x.py"\n'
        '--- "a/tests/test x.py"\n'
        '+++ "b/tests/test x.py"\n'
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    assert "tests/test x.py" in paths_from_patch(patch)
    assert check_patch(patch, PathsSpec())


def test_deny_wins_over_allow() -> None:
    spec = PathsSpec(allow=["tests/"], deny=[])
    assert check_paths(["tests/test_core.py"], spec)


def test_allow_list_is_enforced() -> None:
    spec = PathsSpec(allow=["src/"])
    assert check_paths(["src/works/cli.py"], spec) == []
    violation = check_paths(["docs/readme.md"], spec)
    assert violation and violation[0].reason == "not in the allow list"


def test_flow_deny_adds_to_defaults() -> None:
    assert check_paths(["calc/tools.py"], PathsSpec(deny=["calc/tools.py"]))
    assert check_paths(["calc/core.py"], PathsSpec(deny=["calc/tools.py"])) == []


def test_control_characters_are_unsafe() -> None:
    assert is_unsafe("calc/\x00core.py")
    assert check_paths(["calc/\x00core.py"], PathsSpec())


def test_paths_from_patch_reads_both_sides_and_renames() -> None:
    patch = "\n".join(
        [
            "diff --git a/calc/core.py b/calc/core.py",
            "--- a/calc/core.py",
            "+++ b/calc/core.py",
            "@@ -1 +1 @@",
            "-x",
            "+y",
            "diff --git a/old.py b/new.py",
            "similarity index 90%",
            "rename from old.py",
            "rename to new.py",
            "diff --git a/gone.py b/gone.py",
            "--- a/gone.py",
            "+++ /dev/null",
        ]
    )
    paths = paths_from_patch(patch)
    assert "calc/core.py" in paths
    assert "new.py" in paths
    assert "old.py" in paths or "new.py" in paths
    assert "/dev/null" not in paths


def test_check_patch_refuses_a_test_edit() -> None:
    patch = "\n".join(
        [
            "diff --git a/tests/test_core.py b/tests/test_core.py",
            "--- a/tests/test_core.py",
            "+++ b/tests/test_core.py",
            "@@ -5,2 +5,2 @@",
            "-    assert add(2, 3) == 5",
            "+    assert add(2, 3) == -1",
        ]
    )
    assert check_patch(patch, PathsSpec())


@given(
    st.lists(
        st.text(alphabet="abc/._- \\", min_size=0, max_size=12),
        min_size=1,
        max_size=4,
    ).map("/".join)
)
@settings(max_examples=200, deadline=None)
def test_paths_containing_dotdot_are_always_unsafe(path: str) -> None:
    if ".." in path.replace("\\", "/").split("/"):
        assert is_unsafe(path)
        assert check_paths([path], PathsSpec())
