"""One exact business code and its authored meaning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.domain.value_objects.business_code import BusinessCode
from domain_kernel.shared.domain.value_objects.label_text import LabelText
from domain_kernel.shared.domain.value_objects.meaning_text import MeaningText
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.domain.value_objects.terminology import EMPTY_TERMINOLOGY, Terminology
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True)
class ValueSetMember:
    """One exact business code and its authored meaning."""

    code: BusinessCode
    label: LabelText
    meaning: MeaningText
    ontology_term: OntologyTermReference | None = None
    terminology: Terminology = EMPTY_TERMINOLOGY
    unit: DefinitionReference | None = None

    def __post_init__(self) -> None:
        """Validate the vocabulary member and its exclusive unit bindings."""
        RuntimeTypeValidation.require_exact(
            value=self.code, expected=BusinessCode, field="Member code"
        )
        RuntimeTypeValidation.require_exact(
            value=self.label, expected=LabelText, field="Member label"
        )
        RuntimeTypeValidation.require_exact(
            value=self.meaning, expected=MeaningText, field="Member meaning"
        )
        RuntimeTypeValidation.require_exact(
            value=self.terminology, expected=Terminology, field="Member terminology"
        )
        if self.ontology_term is not None:
            RuntimeTypeValidation.require_exact(
                value=self.ontology_term, expected=OntologyTermReference, field="Member term"
            )
        if self.unit is not None:
            ShapeFieldValidation.require_definition_reference(value=self.unit, field="Member unit")
            if self.ontology_term is not None:
                raise ValueError("Supply a unit or ontology term for a code, never both")
