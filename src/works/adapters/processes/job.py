"""Kill a supervised child tree together with Works, even on a hard kill.

On Windows the child is placed in a Job Object with `KILL_ON_JOB_CLOSE`: when Works dies
(including TerminateProcess) the handle closes and the whole tree is killed. POSIX already
starts each command in its own session and kills the group on cancellation; a hard `SIGKILL`
of the daemon can still orphan a child, which `docs/reference/reliability.md` records as the
remaining gap.
"""

from __future__ import annotations

import sys
from typing import Any

# A plain str keeps both branches reachable for mypy when it checks `--platform linux`.
_PLATFORM: str = sys.platform

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def attach(process: Any) -> Any:
    """Return a platform handle that must be closed when the process ends."""
    if _PLATFORM != "win32":
        return None
    return _attach_windows(process)


def release(handle: Any) -> None:
    """Close the handle; on Windows this kills any process still in the job."""
    if handle is None or _PLATFORM != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]


def _attach_windows(process: Any) -> Any:
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    ):
        kernel32.CloseHandle(job)
        return None
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
        kernel32.CloseHandle(job)
        return None
    return job
