from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from works.domain.flow import PathsSpec
from works.domain.policy import (
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


def test_an_unparseable_quoted_path_is_refused() -> None:
    assert is_unsafe('"a/tests/broken.py')
    assert check_paths(['"a/tests/broken.py'], PathsSpec())


def test_a_directory_named_tests_is_denied_at_any_depth() -> None:
    assert check_paths(["tests"], PathsSpec())
    assert check_paths(["pkg/tests"], PathsSpec())
    assert check_paths(["a/b/tests/c.py"], PathsSpec())


def test_unicode_is_normalised_before_matching() -> None:
    assert normalize_path("te\u0301sts/x") == normalize_path("tésts/x")
    assert check_paths(["te\u0301sts/test.py"], PathsSpec()) == []


def test_paths_from_a_rename_and_a_delete() -> None:
    patch = "\n".join(
        [
            "diff --git a/old.py b/new.py",
            "rename from old.py",
            "rename to new.py",
            "diff --git a/gone.py b/gone.py",
            "deleted file mode 100644",
            "--- a/gone.py",
            "+++ /dev/null",
        ]
    )
    paths = paths_from_patch(patch)
    assert "new.py" in paths
    assert "gone.py" in paths
    assert "/dev/null" not in paths


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a//b", "a/b"),
        ("a/./b", "a/b"),
        ("a/.../b", "a/b"),
        ("a/b ", "a/b"),
        ("C:\\a\\b", "C:/a/b"),
        ("   ", ""),
        ("a/é/../b", "a/é/../b"),
    ],
)
def test_normalize_path_matches_the_documented_rules(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


@pytest.mark.parametrize(
    "path",
    ["a\tb", 'a"b', "~", "a/..", "a:b", "\\server\share"],
)
def test_is_unsafe_covers_each_refusal_rule(path: str) -> None:
    assert is_unsafe(path)


@pytest.mark.parametrize("path", ["a", ":", "ab:c", "a/.../b", "a/b"])
def test_is_unsafe_does_not_over_refuse(path: str) -> None:
    assert not is_unsafe(path)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("tests", "**/tests/", True),
        ("pkg/TESTS/x.py", "**/tests/", True),
        ("x/tests", "**/tests/", True),
        ("testsx/a.py", "**/tests/", False),
        ("mytests/a.py", "**/tests/", False),
        ("calc/tools.py", "calc/", True),
        ("calc", "calc/", True),
        ("calculator/x.py", "calc/", False),
        ("a.py", "", False),
    ],
)
def test_matches_globs_and_directories(path: str, pattern: str, expected: bool) -> None:
    from works.domain.policy import matches

    assert matches(path, [pattern]) is expected


def test_refusal_reasons_are_exact() -> None:
    unsafe = check_paths(["../x"], PathsSpec())
    assert unsafe[0].reason == "unsafe path (absolute, drive or ..)"

    empty = check_paths([" . "], PathsSpec())
    assert empty and empty[0].reason == "empty path"

    denied = check_paths(["tests/test_core.py"], PathsSpec())
    assert denied and denied[0].reason == "denied by policy"


def test_a_quoted_path_with_an_escape_is_decoded() -> None:
    patch = (
        'diff --git "a/tests/tab\\there.py" "b/tests/tab\\there.py"\n'
        '--- "a/tests/tab\\there.py"\n'
        '+++ "b/tests/tab\\there.py"\n'
    )
    assert "tests/tab\there.py" in paths_from_patch(patch)


def test_an_unchanged_patch_lists_a_path_once() -> None:
    patch = "\n".join(
        [
            "diff --git a/calc/core.py b/calc/core.py",
            "--- a/calc/core.py",
            "+++ b/calc/core.py",
            "@@ -1 +1 @@",
            "-x",
            "+y",
        ]
    )
    assert paths_from_patch(patch) == ["calc/core.py"]


def test_an_added_file_uses_the_new_side_only() -> None:
    patch = "\n".join(
        ["diff --git a/new.py b/new.py", "new file mode 100644", "--- /dev/null", "+++ b/new.py"]
    )
    assert paths_from_patch(patch) == ["new.py"]


def test_a_tab_separated_timestamp_is_dropped() -> None:
    patch = "diff --git a/x.py b/x.py\n--- a/x.py\t2026-01-01\n+++ b/x.py\t2026-01-01\n"
    assert paths_from_patch(patch) == ["x.py"]
