"""Resolve the immutable reference resources used by a review transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.dependencies import dependency_closure

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
    from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure


async def review_ontology_resources(
    *,
    scope: ModelScope,
    selected: SelectedPacks | None,
    dependencies: Sequence[DomainModelBundle],
) -> tuple[OntologyClosure, ...]:
    """Capture pack references from the selected workspace and its exact dependencies."""
    pack = None if selected is None else await selected.get(scope=scope)
    return (
        *(() if pack is None else pack.ontologies),
        *(
            closure
            for bundle in dependency_closure(scope=scope, bundles=dependencies)
            if bundle.publication.reference_pack is not None
            for closure in bundle.publication.reference_pack.ontologies
        ),
    )
