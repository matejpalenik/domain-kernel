"""Snapshots compared when observing model effects."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ComparisonKind(StrEnum):
    """Snapshots compared when observing model effects."""

    PROPOSAL = "proposal"
    REVISION = "revision"
    BASELINE = "baseline"
    INITIAL = "initial"
