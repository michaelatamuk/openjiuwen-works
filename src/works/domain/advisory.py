"""A dependency advisory carried from intake to the evidence page."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdvisoryRef(BaseModel):
    """The part of a CVE record a task and its proof need to keep."""

    id: str
    package: str
    version: str
    severity: str = "unknown"
    fixed: str | None = None
    cvss: float | None = None
    links: list[str] = Field(default_factory=list)
