from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class InferenceInput:
    """Untrusted source content with the exact issued citations."""

    text: str = field(repr=False)
    evidence: Sequence[Evidence]
    is_table: bool = False

    def __post_init__(self) -> None:
        """Detach the evidence inventory and require explicit content."""
        TextValidation.require_text(value=self.text, field="Inference input")
        RuntimeTypeValidation.require_exact(value=self.is_table, expected=bool, field="Table input")
        items = SequenceValidation.snapshot_sequence(
            items=self.evidence, item_type=Evidence, field="Evidence"
        )
        if not items:
            raise ValueError("Supply an exact citation for inference input")
        object.__setattr__(self, "evidence", items)
