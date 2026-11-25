"""Closed reasoning vocabulary and advertised capability records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


@unique
class ReasoningProfile(StrEnum):
    """The requested language profile."""

    RDFS = "rdfs"
    OWL2_EL = "owl2_el"
    OWL2_QL = "owl2_ql"
    OWL2_RL = "owl2_rl"
    OWL2_DL = "owl2_dl"
    OWL2_FULL = "owl2_full"


@unique
class SemanticRegime(StrEnum):
    """The semantics under which a result is claimed."""

    RDFS = "rdfs"
    OWL_DIRECT = "owl_direct"
    OWL_RDF = "owl_rdf"


@unique
class ReasoningTask(StrEnum):
    """The question put to the selected reasoner."""

    CONSISTENCY = "consistency"
    CLASSIFICATION = "classification"
    ENTAILMENT = "entailment"


@unique
class SemanticStatus(StrEnum):
    """The outcome of optional formal processing."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class ReasoningSupport:
    """One advertised profile, semantic regime and task."""

    profile: ReasoningProfile
    regime: SemanticRegime
    task: ReasoningTask
    complete: bool
    restrictions: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Validate the capability and detach restrictions."""
        require_exact(value=self.profile, expected=ReasoningProfile, field="Reasoning profile")
        require_exact(value=self.regime, expected=SemanticRegime, field="Semantic regime")
        require_exact(value=self.task, expected=ReasoningTask, field="Reasoning task")
        require_exact(value=self.complete, expected=bool, field="Completeness")
        restrictions = snapshot_sequence(
            items=self.restrictions, item_type=str, field="Reasoning restrictions"
        )
        for restriction in restrictions:
            require_text(value=restriction, field="Reasoning restriction")
        object.__setattr__(self, "restrictions", restrictions)
