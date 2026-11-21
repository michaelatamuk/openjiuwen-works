"""Harness adapters. A real adapter lands in M1; the fake one keeps CI honest."""

from __future__ import annotations

from .base import Harness, Proposal, ProposalRequest
from .fake import FakeHarness

__all__ = ["FakeHarness", "Harness", "Proposal", "ProposalRequest"]
