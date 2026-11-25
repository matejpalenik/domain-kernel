"""Localized labels and descriptions authored for one owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.label_role import LabelRole
from domain_kernel.shared.domain.value_objects.localized_description import LocalizedDescription
from domain_kernel.shared.domain.value_objects.localized_label import LocalizedLabel
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.value_objects.label_text import LabelText
    from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag


@dataclass(frozen=True, kw_only=True)
class Terminology:
    """Localized labels and descriptions authored for one owner."""

    labels: Sequence[LocalizedLabel] = ()
    descriptions: Sequence[LocalizedDescription] = ()

    def __post_init__(self) -> None:
        """Snapshot inputs and enforce uniqueness within each language."""
        labels = SequenceValidation.snapshot_sequence(
            items=self.labels, item_type=LocalizedLabel, field="Labels"
        )
        descriptions = SequenceValidation.snapshot_sequence(
            items=self.descriptions, item_type=LocalizedDescription, field="Descriptions"
        )
        preferred: set[LanguageTag] = set()
        roles: dict[tuple[LabelText, LanguageTag], LabelRole] = {}
        for label in labels:
            key = (label.text, label.language)
            if roles.setdefault(key, label.role) is not label.role:
                raise ValueError("Identical text and language cannot have conflicting label roles")
            if label.role is LabelRole.PREFERRED:
                if label.language in preferred:
                    raise ValueError("Each language may have at most one preferred label")
                preferred.add(label.language)
        if len({item.language for item in descriptions}) != len(descriptions):
            raise ValueError("Each language may have at most one description")
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "descriptions", descriptions)


EMPTY_TERMINOLOGY = Terminology()
