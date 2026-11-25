"""Type contract for consumer obligation."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.collection_semantics_obligation import (
    CollectionSemanticsObligation,
)
from domain_kernel.shared.domain.value_objects.key_enforcement_obligation import (
    KeyEnforcementObligation,
)
from domain_kernel.shared.domain.value_objects.reference_target_obligation import (
    ReferenceTargetObligation,
)
from domain_kernel.shared.domain.value_objects.relationship_enforcement_obligation import (
    RelationshipEnforcementObligation,
)

type ConsumerObligation = (
    KeyEnforcementObligation
    | ReferenceTargetObligation
    | RelationshipEnforcementObligation
    | CollectionSemanticsObligation
)
