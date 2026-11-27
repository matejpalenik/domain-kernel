"""An inspected concept with direct, snapshot-local reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.errors.attribute_not_found_error import AttributeNotFoundError
from domain_kernel.shared.domain.errors.key_not_found_error import KeyNotFoundError
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
    from domain_kernel.shared.domain.entities.key_definition import KeyDefinition


@dataclass(frozen=True, kw_only=True)
class Concept(Definition[ConceptDefinition]):
    """An inspected concept with direct, snapshot-local reads."""

    @override
    def __post_init__(self) -> None:
        """Check the specialization while preserving the definition record layout."""
        super().__post_init__()
        RuntimeTypeValidation.require_exact(
            value=self.body, expected=ConceptDefinition, field="Concept body"
        )

    @property
    def attributes(self) -> tuple[AttributeDefinition, ...]:
        """This revision's direct attributes."""
        return tuple(self.body.attributes)

    @property
    def keys(self) -> tuple[KeyDefinition, ...]:
        """This revision's local keys."""
        return tuple(self.body.keys)

    def get_attribute(
        self, *, name: str | None = None, attribute_id: AttributeId | None = None
    ) -> AttributeDefinition:
        """Find one inspected attribute by one exact selector."""
        LookupNamingPolicy.require_selector(name=name, item_id=attribute_id, id_type=AttributeId)

        for attribute in self.body.attributes:
            if attribute.id == attribute_id or attribute.name == name:
                return attribute

        raise AttributeNotFoundError

    def get_key(self, *, name: str | None = None, key_id: KeyId | None = None) -> KeyDefinition:
        """Find one inspected key by one exact selector."""
        LookupNamingPolicy.require_selector(name=name, item_id=key_id, id_type=KeyId)

        for key in self.body.keys:
            if key.id == key_id or key.name == name:
                return key

        raise KeyNotFoundError
