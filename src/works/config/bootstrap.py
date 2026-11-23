"""Startup hygiene. Standard library only, imported before the rest of the package."""

from __future__ import annotations

import os
import sys


def harden_sys_path() -> None:
    """Drop the current directory from `sys.path`.

    `python -m works` puts the working directory first, so a file named `json.py` in the product
    repository would shadow the standard library. The package is imported from its installation,
    so removing the cwd is safe after this module loads.
    """
    cwd = os.getcwd()
    sys.path[:] = [entry for entry in sys.path if entry not in ("", ".", cwd)]
