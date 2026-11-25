"""The requested language profile."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ReasoningProfile(StrEnum):
    """The requested language profile."""

    RDFS = "rdfs"
    OWL2_EL = "owl2_el"
    OWL2_QL = "owl2_ql"
    OWL2_RL = "owl2_rl"
    OWL2_DL = "owl2_dl"
    OWL2_FULL = "owl2_full"
