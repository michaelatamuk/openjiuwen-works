from __future__ import annotations

from works.render import table


def test_a_table_has_headers_a_rule_and_aligned_rows() -> None:
    rendered = table(("id", "state"), [("t-1", "queued"), ("t-2", "proved")])
    lines = rendered.splitlines()
    assert lines[0].startswith("id")
    assert set(lines[1]) == {"-", " "}
    assert "t-1" in lines[2]
    assert "proved" in lines[3]


def test_an_empty_table_is_still_a_table() -> None:
    rendered = table(("id", "state"), [])
    assert rendered.splitlines()[0].startswith("id")
    assert len(rendered.splitlines()) == 2
