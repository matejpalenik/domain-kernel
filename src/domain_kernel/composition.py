"""Assemble immutable publications and select bounded workflow views."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.composition import (
    ModelComposition,
    ModelSlice,
    SliceDefinition,
    TraversalDirection,
    composition_digest,
)
from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.invalid_bundle_error import InvalidBundleError
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.policies.ontology_pins_policy import OntologyPinsPolicy
from domain_kernel.shared.domain.policies.shape_ontology_policy import ShapeOntologyPolicy
from domain_kernel.shared.domain.policies.shape_traversal_policy import ShapeTraversalPolicy
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.scope_mismatch_error import ScopeMismatchError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
    from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
    from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
    from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
        OntologyTermReference,
    )


def _model_order(pin: ModelVersion) -> tuple[str, str, str]:
    return (pin.scope.model_id.value, pin.version, pin.content_hash.value)


def _definition_order(reference: PinnedDefinitionReference) -> tuple[str, str, str, str, int]:
    return (
        *_model_order(reference.model),
        reference.definition_id.value,
        reference.definition_revision,
    )


def _positive(*, value: int, field: str) -> None:
    RuntimeTypeValidation.require_exact(value=value, expected=int, field=field)
    if value < 1:
        message = f"Use a positive {field.lower()}"
        raise ValueError(message)


def _archive_set(*, roots: Sequence[DomainModelBundle]) -> tuple[DomainModelBundle, ...]:
    if not roots:
        raise ValueError("Supply at least one published model")
    project = roots[0].scope.project_id
    selected: dict[ModelScope, DomainModelBundle] = {}

    def include(*, archive: DomainModelBundle) -> None:
        existing = selected.get(archive.scope)
        if existing is not None and existing != archive:
            raise InvalidBundleError(
                issues=(
                    Issue(
                        code="composition_conflict",
                        path=("bundles", archive.scope.model_id.value),
                        message="Compose one exact publication per model.",
                    ),
                ),
            )
        selected[archive.scope] = archive

    for root in roots:
        if root.scope.project_id != project:
            raise ScopeMismatchError
        include(archive=root)
        for dependency in dependency_closure(
            scope=root.scope,
            bundles=root.publication.candidate.dependency_bundles,
        ):
            include(archive=dependency)
    return tuple(sorted(selected.values(), key=lambda archive: _model_order(archive.model_version)))


def compose_models(
    *,
    bundles: Sequence[DomainModelBundle],
    max_bytes: int = 64 * 1024 * 1024,
) -> ModelComposition:
    """Verify and assemble exact same-project releases without accessing producer state."""
    _positive(value=max_bytes, field="Byte limit")
    roots = SequenceValidation.snapshot_sequence(
        items=bundles, item_type=DomainModelBundle, field="Publications"
    )
    archives = _archive_set(roots=roots)
    used = 0
    for archive in archives:
        used += len(archive.serialize())
        if used > max_bytes:
            raise ResourceLimitError(message="Increase the byte limit or choose fewer publications")
    pins = tuple(sorted({item.model_version for item in roots}, key=_model_order))
    return ModelComposition(
        roots=pins,
        bundles=archives,
        content_hash=composition_digest(roots=pins, bundles=archives),
    )


def _active_definitions(
    *, composition: ModelComposition
) -> dict[PinnedDefinitionReference, SliceDefinition]:
    archives = {item.model_version: item for item in composition.bundles}
    roots = tuple(archives[pin] for pin in composition.roots)
    if _archive_set(roots=roots) != composition.bundles:
        raise ValueError("Supply the complete canonical closure of the selected roots")
    for root in roots:
        _ = root.serialize()
    result: dict[PinnedDefinitionReference, SliceDefinition] = {}
    for bundle in composition.bundles:
        for item in bundle.content.definitions:
            if item.status is not DefinitionStatus.APPROVED:
                continue
            reference = PinnedDefinitionReference(
                model=bundle.model_version,
                definition_id=item.id,
                definition_revision=item.revision,
            )
            result[reference] = SliceDefinition(reference=reference, definition=item)
    return result


def _connections(
    *,
    definitions: Mapping[PinnedDefinitionReference, SliceDefinition],
    archives: Sequence[DomainModelBundle],
) -> tuple[
    dict[PinnedDefinitionReference, set[PinnedDefinitionReference]],
    dict[PinnedDefinitionReference, set[PinnedDefinitionReference]],
]:
    local = {(ref.model, ref.definition_id): ref for ref in definitions}
    outgoing: dict[PinnedDefinitionReference, set[PinnedDefinitionReference]] = {
        ref: set() for ref in definitions
    }
    incoming: dict[PinnedDefinitionReference, set[PinnedDefinitionReference]] = {
        ref: set() for ref in definitions
    }
    dependencies = {
        archive.model_version: frozenset(
            item.model_version
            for item in dependency_closure(
                scope=archive.scope,
                bundles=archive.publication.candidate.dependency_bundles,
            )
        )
        for archive in archives
    }
    modules: dict[OntologyTermReference, set[PinnedDefinitionReference]] = {}
    for owner, captured in definitions.items():
        body = captured.definition.body
        if isinstance(body, OntologyModuleDefinition):
            for resource in body.ontology.documents:
                for term in resource.terms:
                    modules.setdefault(term, set()).add(owner)
    for owner, captured in definitions.items():
        for edge in ShapeTraversalPolicy.shape_references(body=captured.definition.body):
            target = edge.target
            qualified = (
                local.get((owner.model, target)) if isinstance(target, DefinitionId) else target
            )
            if not isinstance(qualified, PinnedDefinitionReference) or qualified not in definitions:
                raise InvalidBundleError(
                    issues=(
                        Issue(
                            code="unresolved_slice_edge",
                            path=edge.path,
                            message="Supply the exact publication of the required edge target.",
                        ),
                    ),
                )
            outgoing[owner].add(qualified)
            incoming[qualified].add(owner)
        for term in ShapeOntologyPolicy.shape_ontology_terms(body=captured.definition.body):
            candidates = modules.get(term, set())
            local_modules = {
                candidate for candidate in candidates if candidate.model == owner.model
            }
            for module in local_modules or {
                item for item in candidates if item.model in dependencies[owner.model]
            }:
                outgoing[owner].add(module)
                incoming[module].add(owner)
    return outgoing, incoming


def _walk(
    *,
    seeds: Iterable[PinnedDefinitionReference],
    edges: Mapping[PinnedDefinitionReference, set[PinnedDefinitionReference]],
    max_hops: int | None,
    limit: int,
) -> set[PinnedDefinitionReference]:
    visited = set(seeds)
    if len(visited) > limit:
        raise ResourceLimitError(message="Select fewer seed definitions or increase the limit")
    queue = deque((item, 0) for item in visited)
    while queue:
        node, distance = queue.popleft()
        if max_hops is not None and distance >= max_hops:
            continue
        for target in edges[node]:
            if target in visited:
                continue
            if len(visited) == limit:
                raise ResourceLimitError(message="Increase the definition limit or narrow the view")
            visited.add(target)
            queue.append((target, distance + 1))
    return visited


def _slice_ontologies(
    *,
    definitions: Sequence[SliceDefinition],
    packs: Sequence[ReferencePack],
) -> tuple[OntologyClosure, ...]:
    closures = {closure.pin: closure for pack in packs for closure in pack.ontologies}
    for item in definitions:
        body = item.definition.body
        if isinstance(body, OntologyModuleDefinition):
            closures[body.ontology.pin] = body.ontology
    return tuple(
        sorted(
            closures.values(),
            key=lambda item: (OntologyPinsPolicy.pin_key(pin=item.root), item.content_hash.value),
        )
    )


def slice_model(  # noqa: PLR0913 - Expose the exact selection and independent resource bounds.
    *,
    composition: ModelComposition,
    seeds: Sequence[PinnedDefinitionReference],
    max_hops: int = 0,
    direction: TraversalDirection = TraversalDirection.BOTH,
    max_definitions: int = 10_000,
    max_bytes: int = 64 * 1024 * 1024,
) -> ModelSlice:
    """Select by hop count, then materialize every required outgoing reference."""
    RuntimeTypeValidation.require_exact(
        value=composition, expected=ModelComposition, field="Model composition"
    )
    RuntimeTypeValidation.require_exact(
        value=direction, expected=TraversalDirection, field="Traversal direction"
    )
    RuntimeTypeValidation.require_exact(value=max_hops, expected=int, field="Hop limit")
    if max_hops < 0:
        raise ValueError("Use a nonnegative hop limit")
    _positive(value=max_definitions, field="Definition limit")
    _positive(value=max_bytes, field="Byte limit")
    supplied = SequenceValidation.snapshot_sequence(
        items=seeds, item_type=PinnedDefinitionReference, field="Seeds"
    )
    if not supplied:
        raise ValueError("Supply at least one exact workflow seed")
    anchors = tuple(sorted(set(supplied), key=_definition_order))
    definitions = _active_definitions(composition=composition)
    if any(seed not in definitions for seed in anchors):
        raise ValueError("Use an active definition at its exact published revision")
    outgoing, incoming = _connections(definitions=definitions, archives=composition.bundles)
    match direction:
        case TraversalDirection.OUTGOING:
            edges = outgoing
        case TraversalDirection.INCOMING:
            edges = incoming
        case TraversalDirection.BOTH:
            edges = {item: outgoing[item] | incoming[item] for item in definitions}
    chosen = _walk(seeds=anchors, edges=edges, max_hops=max_hops, limit=max_definitions)
    complete = _walk(seeds=chosen, edges=outgoing, max_hops=None, limit=max_definitions)
    selected = tuple(definitions[item] for item in sorted(chosen, key=_definition_order))
    support = tuple(definitions[item] for item in sorted(complete - chosen, key=_definition_order))
    models = tuple(sorted({item.model for item in complete}, key=_model_order))
    packs: dict[ReferencePackPin, ReferencePack] = {}
    for bundle in composition.bundles:
        pack = bundle.publication.reference_pack
        if bundle.model_version in models and pack is not None:
            packs[pack.pin] = pack
    resources = tuple(packs.values())
    ontologies = _slice_ontologies(definitions=(*selected, *support), packs=resources)
    payload = CanonicalJson.encode(
        value=RecordCodec.to_value(
            value=(
                "slice-v1",
                composition.content_hash,
                anchors,
                max_hops,
                direction.value,
                models,
                tuple((item.reference, item.definition) for item in selected),
                tuple((item.reference, item.definition) for item in support),
                tuple(pack.pin for pack in resources),
                *((tuple(item.pin for item in ontologies),) if ontologies else ()),
            )
        ),
    )
    if len(payload) + sum(len(pack.serialize()) for pack in resources) > max_bytes:
        raise ResourceLimitError(
            message="Increase the byte limit or select a smaller workflow view"
        )
    return ModelSlice(
        composition_hash=composition.content_hash,
        models=models,
        seeds=anchors,
        selected=selected,
        support=support,
        reference_packs=resources,
        ontologies=ontologies,
        max_hops=max_hops,
        direction=direction,
        content_hash=Hashing.hash_bytes(content=payload),
    )
