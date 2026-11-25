"""One advertised profile, semantic regime and task."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.reasoning_profile import ReasoningProfile
from domain_kernel.shared.domain.enums.reasoning_task import ReasoningTask
from domain_kernel.shared.domain.enums.semantic_regime import SemanticRegime
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


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
        RuntimeTypeValidation.require_exact(
            value=self.profile, expected=ReasoningProfile, field="Reasoning profile"
        )
        RuntimeTypeValidation.require_exact(
            value=self.regime, expected=SemanticRegime, field="Semantic regime"
        )
        RuntimeTypeValidation.require_exact(
            value=self.task, expected=ReasoningTask, field="Reasoning task"
        )
        RuntimeTypeValidation.require_exact(
            value=self.complete, expected=bool, field="Completeness"
        )
        restrictions = SequenceValidation.snapshot_sequence(
            items=self.restrictions, item_type=str, field="Reasoning restrictions"
        )
        for restriction in restrictions:
            TextValidation.require_text(value=restriction, field="Reasoning restriction")
        object.__setattr__(self, "restrictions", restrictions)
