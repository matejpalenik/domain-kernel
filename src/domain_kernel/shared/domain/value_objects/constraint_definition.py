"""Inert, attributed constraint text for later interpretation."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.enums.constraint_language import ConstraintLanguage
from domain_kernel.shared.domain.enums.constraint_target import ConstraintTarget
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class ConstraintDefinition:
    """Inert, attributed constraint text for later interpretation."""

    id: str
    description: str
    language: ConstraintLanguage
    expression: str
    target: ConstraintTarget = ConstraintTarget.MODEL

    def __post_init__(self) -> None:
        """Keep authored constraint text inert and validate its declared target."""
        TextValidation.require_text(value=self.id, field="Constraint ID")
        TextValidation.require_text(value=self.description, field="Constraint description")
        TextValidation.require_text(value=self.expression, field="Constraint expression")
        RuntimeTypeValidation.require_exact(
            value=self.language, expected=ConstraintLanguage, field="Constraint language"
        )
        RuntimeTypeValidation.require_exact(
            value=self.target, expected=ConstraintTarget, field="Constraint target"
        )
