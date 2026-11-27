from __future__ import annotations

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)

type CompanyDefinitionReference = DefinitionId | PinnedDefinitionReference
