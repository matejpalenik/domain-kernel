"""One authored label and its explicit language and role."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.enums.label_role import LabelRole
from domain_kernel.shared.domain.value_objects.label_text import LabelText
from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class LocalizedLabel:
    """One authored label and its explicit language and role."""

    text: LabelText
    language: LanguageTag
    role: LabelRole = LabelRole.PREFERRED

    def __post_init__(self) -> None:
        """Require a typed label, language and role."""
        RuntimeTypeValidation.require_exact(value=self.text, expected=LabelText, field="Label text")
        RuntimeTypeValidation.require_exact(
            value=self.language, expected=LanguageTag, field="Label language"
        )
        RuntimeTypeValidation.require_exact(value=self.role, expected=LabelRole, field="Label role")
