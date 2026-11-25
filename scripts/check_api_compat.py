"""Fail when the current OpenAPI schema removes or narrows something the baseline promised.

Usage:
    python scripts/check_api_compat.py docs/reference/openapi.baseline.json docs/reference/openapi.json

`--update` copies the current schema over the baseline. Do that only when a breaking change is
deliberate and the ADR records it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: not an OpenAPI object")
    return payload


def operations(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path, item in (schema.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method.lower() in HTTP_METHODS and isinstance(operation, dict):
                found[f"{method.upper()} {path}"] = operation
    return found


def parameter_names(operation: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name"))
        for item in operation.get("parameters") or []
        if isinstance(item, dict) and item.get("name")
    }


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    base_ops = operations(baseline)
    cur_ops = operations(current)
    for key, operation in sorted(base_ops.items()):
        if key not in cur_ops:
            problems.append(f"removed operation {key}")
            continue
        removed = parameter_names(operation) - parameter_names(cur_ops[key])
        for name in sorted(removed):
            problems.append(f"{key}: parameter {name} removed")

    base_schemas = (baseline.get("components") or {}).get("schemas") or {}
    cur_schemas = (current.get("components") or {}).get("schemas") or {}
    for name, base in sorted(base_schemas.items()):
        if not isinstance(base, dict):
            continue
        cur = cur_schemas.get(name)
        if cur is None:
            problems.append(f"removed schema {name}")
            continue
        base_props = base.get("properties") or {}
        cur_props = cur.get("properties") or {}
        for prop, spec in sorted(base_props.items()):
            if prop not in cur_props:
                problems.append(f"{name}.{prop} removed")
                continue
            base_type = (spec or {}).get("type")
            cur_type = (cur_props[prop] or {}).get("type")
            if base_type and cur_type and base_type != cur_type:
                problems.append(f"{name}.{prop} type {base_type} -> {cur_type}")
        base_required = set(base.get("required") or [])
        cur_required = set(cur.get("required") or [])
        for prop in sorted(base_required - cur_required):
            problems.append(f"{name}.{prop} is no longer required")
        for prop in sorted(cur_required - base_required):
            problems.append(f"{name}.{prop} became required")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    update = "--update" in args
    args = [item for item in args if item != "--update"]
    if len(args) != 2:
        print(__doc__)
        return 2
    baseline_path, current_path = Path(args[0]), Path(args[1])
    if update:
        shutil.copyfile(current_path, baseline_path)
        print(f"baseline updated from {current_path}")
        return 0
    problems = compare(load(baseline_path), load(current_path))
    for problem in problems:
        print(f"breaking: {problem}")
    print(f"api compatibility: {len(problems)} breaking change(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
