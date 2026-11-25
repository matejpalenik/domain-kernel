"""Type contract for attribute type."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType

type AttributeType = ScalarValueType | ConceptReferenceType | ValueSetType | StructuredValueType
