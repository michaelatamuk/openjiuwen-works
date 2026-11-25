import subprocess
import sys

import pytest

from works.adapters.processes import job

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows Job Objects are the mechanism under test"
)


def test_releasing_the_job_kills_the_child_tree() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        handle = job.attach(process)
        assert handle is not None, "the job object could not be created"
        job.release(handle)
        process.wait(timeout=10)
        assert process.returncode is not None
    finally:
        if process.poll() is None:
            process.kill()
