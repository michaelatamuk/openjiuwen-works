"""Write the OpenAPI schema used to generate the TypeScript client.

    python scripts/dump_openapi.py --update
    python scripts/dump_openapi.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))

from works.interfaces.api.app import create_app  # noqa: E402

TARGET = FACTORY / "docs" / "reference" / "openapi.json"


def schema() -> dict[str, object]:
    return create_app().openapi()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--update", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = json.dumps(schema(), indent=2, sort_keys=True) + "\n"
    if args.update:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {TARGET.relative_to(FACTORY)}")
        return
    if not TARGET.exists():
        raise SystemExit(f"missing {TARGET.relative_to(FACTORY)}; run with --update")
    if TARGET.read_text(encoding="utf-8") != rendered:
        raise SystemExit(f"{TARGET.relative_to(FACTORY)} is stale; run with --update")
    print("openapi schema is current")


if __name__ == "__main__":
    main()
