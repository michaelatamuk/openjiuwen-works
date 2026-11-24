"""The supervisor owns the loop. CLI commands only call it; they never act on their own."""

from __future__ import annotations

from works.application.supervisor.core import Supervisor

__all__ = ["Supervisor"]
