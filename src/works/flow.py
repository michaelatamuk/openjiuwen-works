"""Flows are node graphs. Policy is data, enforced by the runner, never by the model."""

from __future__ import annotations

import shlex
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from .errors import ConfigError
from .records import Budget

DEFAULT_PYTHON = sys.executable


class NodeKind(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENTIC = "agentic"


class GateMode(StrEnum):
    """A new gate earns enforcement; it does not start there."""

    OFF = "off"
    OBSERVE = "observe"
    ENFORCE = "enforce"


class Node(BaseModel):
    id: str = Field(min_length=1)
    kind: NodeKind
    cmd: str | None = None
    required: bool = True
    timeout_s: int = Field(default=600, gt=0)
    mode: GateMode = GateMode.ENFORCE

    @model_validator(mode="after")
    def _check(self) -> Node:
        if self.kind is NodeKind.DETERMINISTIC and not self.cmd:
            raise ValueError(f"deterministic node {self.id!r} needs a cmd")
        return self

    def argv(self, python: str = DEFAULT_PYTHON) -> list[str]:
        if not self.cmd:
            raise ConfigError(f"node {self.id!r} has no command")
        return [part.replace("{python}", python) for part in shlex.split(self.cmd)]


class Repair(BaseModel):
    attempts: int = Field(default=1, ge=0, le=5)
    then: str = "needs_person"


class Gate(BaseModel):
    on: str
    action: str = "ask"
    when_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Gate:
        if self.on not in ("plan", "release"):
            raise ValueError(f"unknown gate {self.on!r}; expected plan or release")
        if self.action not in ("ask", "allow"):
            raise ValueError(f"unknown gate action {self.action!r}; expected ask or allow")
        return self


class PathsSpec(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class RiskSpec(BaseModel):
    """Which paths always need an owner, and who owns them."""

    high_paths: list[str] = Field(
        default_factory=lambda: [
            "auth/",
            "billing/",
            "migrations/",
            "secrets/",
            ".github/",
            "flows/",
            "src/works/policy.py",
            "src/works/state.py",
            "src/works/scenarios.py",
        ]
    )
    owners: dict[str, list[str]] = Field(default_factory=dict)


class FlowSpec(BaseModel):
    schema_version: int = 1
    flow: str
    product: str
    nodes: list[Node]
    edges: list[tuple[str, str]] = Field(default_factory=list)
    repair: Repair = Field(default_factory=Repair)
    paths: PathsSpec = Field(default_factory=PathsSpec)
    budget: Budget = Field(default_factory=Budget)
    gates: list[Gate] = Field(default_factory=list)
    mode: GateMode = GateMode.ENFORCE
    risk: RiskSpec = Field(default_factory=RiskSpec)

    @model_validator(mode="after")
    def _check_graph(self) -> FlowSpec:
        ids = [node.id for node in self.nodes]
        if not ids:
            raise ValueError("a flow needs at least one node")
        if len(ids) != len(set(ids)):
            raise ValueError("node ids must be unique")
        for src, dst in self.edges:
            if src not in ids or dst not in ids:
                raise ValueError(f"edge {src!r} -> {dst!r} references an unknown node")
        self._topological_order()
        return self

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise ConfigError(f"flow {self.flow!r} has no node {node_id!r}")

    def gate(self, on: str) -> Gate:
        for gate in self.gates:
            if gate.on == on:
                return gate
        return Gate(on=on, action="ask")

    def _topological_order(self) -> list[str]:
        indegree = {node.id: 0 for node in self.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for src, dst in self.edges:
            indegree[dst] += 1
            outgoing[src].append(dst)
        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for nxt in outgoing[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
        if len(order) != len(self.nodes):
            raise ValueError("edges contain a cycle")
        return order


def load_flow(path: Path) -> FlowSpec:
    if not path.exists():
        raise ConfigError(f"flow not found: {path}")
    return load_flow_text(path.read_text(encoding="utf-8"), source=str(path))


def load_flow_text(text: str, *, source: str = "<memory>") -> FlowSpec:
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{source} must contain a mapping")
    try:
        return FlowSpec.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{source} is not a valid flow:\n{exc}") from exc


def find_flow(flows_dir: Path, name: str) -> Path:
    candidate = flows_dir / f"{name}.yaml"
    if candidate.exists():
        return candidate
    raise ConfigError(f"flow not found: {candidate}")
