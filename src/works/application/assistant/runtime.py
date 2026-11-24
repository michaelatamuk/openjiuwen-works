"""Where the Mira worker lives and how to start it."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from works.config.resources import worker
from works.domain.errors import ConfigError

WORKER = worker("agent_chat_worker.py")
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE = "https://api.deepseek.com/anthropic"


def agent_python() -> Path:
    return Path(
        os.environ.get("WORKS_AGENT_PYTHON")
        or r"C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe"
    )


def agent_core() -> Path:
    return Path(os.environ.get("WORKS_AGENT_CORE") or r"C:\Workspace\openjiuwen\agent-core")


def availability() -> dict[str, Any]:
    key = os.environ.get("WORKS_MODEL_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    python = agent_python()
    core = agent_core()
    available = bool(key) and python.exists() and core.exists() and WORKER is not None
    reason = ""
    if not key:
        reason = "no model key: set ANTHROPIC_API_KEY or WORKS_MODEL_KEY"
    elif not python.exists():
        reason = f"agent-core Python not found: {python}"
    elif not core.exists():
        reason = f"agent-core checkout not found: {core}"
    elif WORKER is None:
        reason = "agent chat worker not found"
    return {
        "available": available,
        "reason": reason,
        "model": os.environ.get("WORKS_AGENT_MODEL") or DEFAULT_MODEL,
        "base": os.environ.get("WORKS_MODEL_BASE") or DEFAULT_BASE,
    }


def command() -> list[str]:
    state = availability()
    if not state["available"] or WORKER is None:
        raise ConfigError(f"Mira is not available: {state['reason']}")
    return [str(agent_python()), str(WORKER)]


def environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[3]), str(agent_core()), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    env.setdefault("WORKS_AGENT_MODEL", DEFAULT_MODEL)
    env.setdefault("WORKS_MODEL_BASE", DEFAULT_BASE)
    return env
