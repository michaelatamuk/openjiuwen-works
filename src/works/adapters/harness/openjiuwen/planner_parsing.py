"""Parsing the planner and critic JSON turns."""

from __future__ import annotations

import json
import re
from typing import Any

from works.adapters.harness.openjiuwen.providers import ProviderName, validate_provider
from works.application.planning.service import PlanCritique, PlanProposal
from works.domain.errors import ConfigError

_PLAN_PROVIDERS = frozenset({"claudecode", "native"})


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _json_object(text: str, what: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text)
    if match is None:
        raise ConfigError(f"the {what} returned no JSON object")
    try:
        payload: Any = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"the {what} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"the {what} returned a non-object JSON value")
    return payload


def parse_plan_json(text: str) -> PlanProposal:
    try:
        return PlanProposal.model_validate(_json_object(text, "planner"))
    except ValueError as exc:
        raise ConfigError(f"the planner proposal is invalid: {exc}") from exc


def parse_critique_json(text: str) -> PlanCritique:
    try:
        return PlanCritique.model_validate(_json_object(text, "critic"))
    except ValueError as exc:
        raise ConfigError(f"the critic verdict is invalid: {exc}") from exc


def _validate_plan_provider(provider: str) -> ProviderName:
    selected = validate_provider(provider, env_name="planner provider")
    if selected not in _PLAN_PROVIDERS:
        raise ConfigError(
            f"the planner does not support {selected!r} yet; use claudecode or native"
        )
    return selected
