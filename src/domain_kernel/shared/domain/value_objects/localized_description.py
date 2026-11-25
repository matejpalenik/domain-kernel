"""One authored description in its declared language."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag
from domain_kernel.shared.domain.value_objects.meaning_text import MeaningText
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class LocalizedDescription:
    """One authored description in its declared language."""

    text: MeaningText
    language: LanguageTag

    def __post_init__(self) -> None:
        """Keep descriptive meaning separate from display labels."""
        RuntimeTypeValidation.require_exact(
            value=self.text, expected=MeaningText, field="Description text"
        )
        RuntimeTypeValidation.require_exact(
            value=self.language, expected=LanguageTag, field="Description language"
        )
