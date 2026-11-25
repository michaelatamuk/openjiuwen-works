"""On Linux the command must not outlive a daemon that was killed with SIGKILL."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is a Linux facility"
)

_HELPER = """
import os
import signal
import sys
import threading
import time
from pathlib import Path

from works.adapters.processes.runner import SubprocessRunner

pid_file = Path(sys.argv[1])
inner = (
    "import os, sys, time; "
    "open(sys.argv[1], 'w').write(str(os.getpid())); "
    "time.sleep(60)"
)
command = [sys.executable, "-c", inner, str(pid_file)]
thread = threading.Thread(
    target=lambda: SubprocessRunner().run(command, Path.cwd(), timeout_s=60), daemon=True
)
thread.start()
deadline = time.monotonic() + 30
while not pid_file.exists() and time.monotonic() < deadline:
    time.sleep(0.05)
os.kill(os.getpid(), signal.SIGKILL)
"""


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_hard_killed_parent_takes_the_command_with_it(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    parent = subprocess.Popen(
        [sys.executable, "-c", _HELPER, str(pid_file)],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    parent.wait(timeout=60)
    assert parent.returncode == -signal.SIGKILL
    assert pid_file.exists(), "the helper died before it could start a command"
    child = int(pid_file.read_text(encoding="utf-8"))
    # The command wrote its own pid, so it really existed; the only thing that can end it now is
    # the parent-death signal.
    deadline = time.monotonic() + 10
    while _running(child) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _running(child), json.dumps({"orphan_pid": child, "parent": parent.pid})
