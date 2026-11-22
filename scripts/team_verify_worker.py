"""Run the deterministic verification team inside the agent-core environment.

This script is invoked by `works team verify` with agent-core's Python, so Works itself does not
need agent-core's UI/runtime dependency tree.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from works.team_verify import VerificationTeam


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    output = Path(sys.argv[1])
    team = VerificationTeam()
    result = asyncio.run(team.verify(payload))
    output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
