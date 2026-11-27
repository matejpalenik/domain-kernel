from __future__ import annotations

from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.domain.types.company_definition_reference import (
    CompanyDefinitionReference,
)

type DefinitionReference = CompanyDefinitionReference | ReferenceDefinitionId
