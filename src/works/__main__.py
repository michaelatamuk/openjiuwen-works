from __future__ import annotations

from .config.bootstrap import harden_sys_path

harden_sys_path()

from .interfaces.cli.main import main_entry  # noqa: E402 - hardening must run first

if __name__ == "__main__":
    main_entry()
