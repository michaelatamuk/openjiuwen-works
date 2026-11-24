"""The handler contract: only the fields a handler changes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from works.domain.records import Event, Task

Fields = dict[str, Any]
Handler = Callable[[Event, Task], Fields | None]
