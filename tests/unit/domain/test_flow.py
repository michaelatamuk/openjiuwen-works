from __future__ import annotations

import sys
from pathlib import Path

import pytest

from works.domain.errors import ConfigError
from works.domain.flow import find_flow, load_flow


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def base_flow(*, nodes: str, edges: str = "", extra: str = "") -> str:
    edge_block = "\n" + edges if edges.strip() else " []"
    return f"""
schema_version: 1
flow: demo
product: openjiuwen
nodes:
{nodes}
edges:{edge_block}
{extra}
"""


def test_loads_the_shipped_flow(paths) -> None:
    flow = load_flow(find_flow(paths.flows, "fix-issue"))
    assert flow.flow == "fix-issue"
    assert flow.node("reproduce").cmd
    assert flow.gate("plan").action == "ask"
    assert set(flow._topological_order()) == {node.id for node in flow.nodes}


def test_node_command_substitutes_python(tmp_path: Path) -> None:
    flow = load_flow(
        write(
            tmp_path / "demo.yaml",
            base_flow(
                nodes='  - id: run\n    kind: deterministic\n    cmd: "{python} -m pytest -q"'
            ),
        )
    )
    argv = flow.node("run").argv("/usr/bin/python3")
    assert argv == ["/usr/bin/python3", "-m", "pytest", "-q"]


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path / "demo.yaml",
        base_flow(
            nodes="  - id: a\n    kind: agentic\n  - id: a\n    kind: agentic",
        ),
    )
    with pytest.raises(ConfigError):
        load_flow(path)


def test_cycles_are_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path / "demo.yaml",
        base_flow(
            nodes="  - id: a\n    kind: agentic\n  - id: b\n    kind: agentic",
            edges="  - [a, b]\n  - [b, a]",
        ),
    )
    with pytest.raises(ConfigError):
        load_flow(path)


def test_unknown_edges_are_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path / "demo.yaml",
        base_flow(nodes="  - id: a\n    kind: agentic", edges="  - [a, ghost]"),
    )
    with pytest.raises(ConfigError):
        load_flow(path)


def test_deterministic_nodes_need_a_command(tmp_path: Path) -> None:
    path = write(tmp_path / "demo.yaml", base_flow(nodes="  - id: a\n    kind: deterministic"))
    with pytest.raises(ConfigError):
        load_flow(path)


def test_unknown_gate_is_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path / "demo.yaml",
        base_flow(
            nodes="  - id: a\n    kind: agentic",
            extra="gates:\n  - on: deploy\n    action: ask",
        ),
    )
    with pytest.raises(ConfigError):
        load_flow(path)


def test_missing_flow_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_flow(tmp_path / "absent.yaml")
    with pytest.raises(ConfigError):
        find_flow(tmp_path, "absent")


def test_argv_defaults_to_the_running_interpreter(tmp_path: Path) -> None:
    flow = load_flow(
        write(
            tmp_path / "demo.yaml",
            base_flow(nodes='  - id: run\n    kind: deterministic\n    cmd: "{python} -c pass"'),
        )
    )
    assert flow.node("run").argv()[0] == sys.executable
