"""Every shipped prompt is registered with its SHA-256, owner and changelog.

A prompt edit changes model behaviour without changing any test input, so the registry makes the
change visible in review: the hash moves, and the entry needs an owner and a changelog line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "flows" / "prompts.lock.json"
DEFAULT_OWNER = "platform"


def prompts() -> list[Path]:
    return sorted((ROOT / "flows").rglob("prompts/*.md"))


def digest(path: Path) -> str:
    """Hash the logical prompt: a CRLF checkout and an LF checkout are the same prompt."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load() -> dict[str, Any]:
    if not REGISTRY.exists():
        return {"schema_version": 1, "prompts": []}
    payload: Any = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("prompts"), list):
        raise SystemExit(f"{REGISTRY}: expected an object with a prompts list")
    return payload


def write(entries: list[dict[str, Any]]) -> None:
    payload = {"schema_version": 1, "prompts": entries}
    REGISTRY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def update() -> None:
    known = {str(item.get("path")): item for item in load()["prompts"]}
    entries: list[dict[str, Any]] = []
    for path in prompts():
        rel = path.relative_to(ROOT).as_posix()
        previous = known.get(rel, {})
        entries.append(
            {
                "name": path.relative_to(ROOT / "flows").as_posix(),
                "path": rel,
                "sha256": digest(path),
                "owner": str(previous.get("owner") or DEFAULT_OWNER),
                "changelog": previous.get("changelog")
                or [
                    {
                        "version": 1,
                        "date": "2026-11-25",
                        "note": "initial registry; hash matches the prompt as shipped",
                    }
                ],
            }
        )
    write(entries)


def problems() -> list[str]:
    registry = load()
    found: list[str] = []
    recorded = {str(item.get("path")): item for item in registry["prompts"]}
    for path in prompts():
        rel = path.relative_to(ROOT).as_posix()
        item = recorded.get(rel)
        if item is None:
            found.append(f"{rel}: not registered; run scripts/check_prompts.py --update")
            continue
        if item.get("sha256") != digest(path):
            found.append(f"{rel}: hash mismatch; the prompt changed without a registry update")
        if not str(item.get("owner") or "").strip():
            found.append(f"{rel}: owner is required")
        changelog = item.get("changelog")
        if not isinstance(changelog, list) or not changelog:
            found.append(f"{rel}: changelog must have at least one entry")
    for rel in recorded:
        if not (ROOT / rel).exists():
            found.append(f"{rel}: registered but missing on disk")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the registry from disk")
    args = parser.parse_args()
    if args.update:
        update()
        print(f"registered {len(prompts())} prompt(s)")
        return 0
    found = problems()
    if found:
        print("\n".join(found))
        print(f"{len(found)} prompt registry problem(s)")
        return 1
    print(f"checked {len(prompts())} prompt(s), all hashes match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
