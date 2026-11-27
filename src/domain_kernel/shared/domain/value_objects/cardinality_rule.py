"""Portable Core count restriction on one directed relationship."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.domain.value_objects.attribute_equals import AttributeEquals
from domain_kernel.shared.domain.value_objects.count import Count
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class CardinalityRule:
    """Portable Core count restriction on one directed relationship."""

    focus: DefinitionReference
    relationship: DefinitionReference
    minimum: Count | None = None
    maximum: Count | None = None
    applicable_class: DefinitionReference | None = None
    when: AttributeEquals | None = None

    def __post_init__(self) -> None:
        """Require valid bounds and at most one applicability condition."""
        ShapeFieldValidation.require_definition_reference(value=self.focus, field="Rule focus")
        ShapeFieldValidation.require_definition_reference(
            value=self.relationship, field="Rule relationship"
        )

        if self.applicable_class is not None:
            ShapeFieldValidation.require_definition_reference(
                value=self.applicable_class, field="Applicable class"
            )

        if self.when is not None:
            RuntimeTypeValidation.require_exact(
                value=self.when, expected=AttributeEquals, field="Rule trigger"
            )
            if self.applicable_class is not None:
                raise ValueError("Use at most one applicability condition.")

        if self.minimum is None and self.maximum is None:
            raise ValueError("Specify at least one rule bound.")
        if self.minimum is not None:
            RuntimeTypeValidation.require_exact(
                value=self.minimum, expected=Count, field="Minimum count"
            )
        if self.maximum is not None:
            RuntimeTypeValidation.require_exact(
                value=self.maximum, expected=Count, field="Maximum count"
            )

        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum.value > self.maximum.value
        ):
            raise ValueError("The maximum count must be at least the minimum.")
