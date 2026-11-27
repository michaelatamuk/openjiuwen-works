"""Render and check the route-class table in docs/reference/platform/http-api.md.

python scripts/dump_route_classes.py --update
python scripts/dump_route_classes.py --check
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))

import works.interfaces.api.routes as routes_pkg  # noqa: E402
from works.interfaces.api.route_classes import ROUTE_CLASSES  # noqa: E402

TARGET = FACTORY / "docs" / "reference" / "platform" / "http-api.md"
START = "<!-- route-classes:start -->"
END = "<!-- route-classes:end -->"
METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"})


def app_routes() -> dict[str, str]:
    """Every operation the routers declare, keyed by 'METHOD /api/v1/path'."""
    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(routes_pkg.__path__):
        module = importlib.import_module(f"{routes_pkg.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        for route in router.routes:
            path = "/api/v1" + str(getattr(route, "path", ""))
            for method in sorted(set(getattr(route, "methods", set()) or set()) & METHODS):
                found[f"{method} {path}"] = info.name
    return found


def problems(routes: dict[str, str]) -> list[str]:
    issues = [f"unclassified route: {key}" for key in sorted(set(routes) - set(ROUTE_CLASSES))]
    issues += [f"stale classification: {key}" for key in sorted(set(ROUTE_CLASSES) - set(routes))]
    return issues


def render() -> str:
    rows = [
        "| Method | Path | Class | Note |",
        "|---|---|---|---|",
    ]
    for key in sorted(ROUTE_CLASSES, key=lambda item: (item.split(" ", 1)[1], item)):
        method, path = key.split(" ", 1)
        route_class, note = ROUTE_CLASSES[key]
        rows.append(f"| {method} | `{path}` | {route_class} | {note} |")
    return "\n".join(rows)


def document_with_table() -> str:
    text = TARGET.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"{TARGET}: add {START} and {END} around the table")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{render()}\n{END}{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--update", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()

    routes = app_routes()
    issues = problems(routes)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    rendered = document_with_table()
    if args.update:
        TARGET.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"updated {TARGET.relative_to(FACTORY)} ({len(routes)} routes)")
        return 0
    if rendered != TARGET.read_text(encoding="utf-8"):
        print(f"{TARGET.relative_to(FACTORY)} is stale; run with --update")
        return 1
    print(f"route classes: {len(routes)} operations classified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
