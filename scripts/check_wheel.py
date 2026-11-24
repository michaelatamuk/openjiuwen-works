"""Fail when a built wheel is missing the runtime bundle, flows or worker scripts.

python scripts/check_wheel.py dist/openjiuwen_works-0.0.1-py3-none-any.whl
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REQUIRED = (
    "works/interfaces/ui/static/dist/index.html",
    "works/py.typed",
    "works/resources/__init__.py",
    "works/resources/flows/fix-issue.yaml",
    "works/resources/flows/fix-issue/prompts/build.md",
    "works/resources/scripts/agent_chat_worker.py",
    "works/resources/scripts/team_verify_worker.py",
    "works/resources/scripts/swarm_adapter.py",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_wheel.py <wheel>", file=sys.stderr)
        return 2
    wheel = Path(sys.argv[1])
    if not wheel.is_file():
        print(f"wheel not found: {wheel}", file=sys.stderr)
        return 2
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = [name for name in REQUIRED if name not in names]
    if missing:
        print(f"{wheel.name} is missing:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        return 1
    print(f"{wheel.name}: runtime bundle, flows and workers present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
