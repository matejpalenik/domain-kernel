"""Copy a published graph with fresh local identities and direct lineage."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel._shared.domain.local_children import copy_local_parts
from domain_kernel._shared.domain.shape_graph import remap_shape
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId

if TYPE_CHECKING:
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.contracts import DefinitionReference, ModelScope


def copy_active_definitions(
    *,
    source: DomainModelBundle,
    scope: ModelScope,
) -> tuple[Definition, ...]:
    """Keep published semantics and set independent model ownership."""
    remapping: dict[DefinitionReference, DefinitionReference] = {}
    copied_ids: dict[DefinitionId, DefinitionId] = {}
    for item in source.content.definitions:
        copied_ids[item.id] = DefinitionId(value=uuid4().hex)
        remapping[item.id] = copied_ids[item.id]
    return tuple(
        replace(
            item,
            id=copied_ids[item.id],
            scope=scope,
            revision=1,
            origin=DefinitionOrigin.BASELINE,
            decision_ids=(),
            rationale=None,
            baseline_definition_id=item.id,
            replacement_ids=(),
            body=copy_local_parts(body=remap_shape(body=item.body, replacements=remapping)),
        )
        for item in source.content.definitions
    )
