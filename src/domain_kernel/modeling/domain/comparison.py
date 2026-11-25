"""Compare exact same-model snapshots or a direct published baseline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    DefinitionChange,
    DefinitionCorrespondence,
    ReferenceDispositionChange,
    SourceAlignmentChange,
)
from domain_kernel.shared.domain.definitions import ConceptDefinition, StructuredValueDefinition
from domain_kernel.shared.domain.lifecycle import definition_change
from domain_kernel.shared.domain.local_children import comparable_shape_bodies
from domain_kernel.shared.domain.model_values import Nullability
from domain_kernel.shared.errors import ScopeMismatchError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.shared.contracts import DefinitionReference, SnapshotReference
    from domain_kernel.shared.domain.data_shapes import AttributeDefinition
    from domain_kernel.shared.domain.definitions import Definition, DefinitionBody


def _baseline_equivalent(
    *,
    original: Definition,
    copy: Definition,
    original_body: DefinitionBody,
    copied_body: DefinitionBody,
) -> bool:
    return (
        original.name == copy.name
        and original.display_name == copy.display_name
        and original.meaning == copy.meaning
        and original.aliases == copy.aliases
        and original.terminology == copy.terminology
        and original.basis is copy.basis
        and original.status is copy.status
        and not copy.decision_ids
        and original_body == copied_body
    )


def _narrowed(*, before: AttributeDefinition, after: AttributeDefinition) -> bool:
    return (
        (not before.required and after.required)
        or (
            before.nullability is Nullability.ALLOWED and after.nullability is Nullability.FORBIDDEN
        )
        or before.collection is not after.collection
        or (
            before.min_items is not None
            and after.min_items is not None
            and before.min_items.value < after.min_items.value
        )
        or (
            after.max_items is not None
            and (before.max_items is None or after.max_items.value < before.max_items.value)
        )
    )


def _breaking(*, change: DefinitionChange) -> bool:
    if not change.before or change.before[0].status is DefinitionStatus.RETIRED:
        return False
    original = change.before[0]
    if change.kind in (DefinitionChangeKind.RETIRE, DefinitionChangeKind.REMOVE):
        return True
    if not change.after:
        return False
    revised = change.after[0]
    if original.kind is not revised.kind:
        return True
    if not isinstance(
        original.body, (ConceptDefinition, StructuredValueDefinition)
    ) or not isinstance(revised.body, (ConceptDefinition, StructuredValueDefinition)):
        return False
    before = {item.name: item for item in original.body.attributes}
    after = {item.name: item for item in revised.body.attributes}
    return (
        bool(before.keys() - after.keys())
        or any(after[name].required for name in after.keys() - before.keys())
        or any(
            _narrowed(before=before[name], after=after[name])
            for name in before.keys() & after.keys()
        )
    )


def _definition_deltas(
    *,
    before: Sequence[Definition],
    after: Sequence[Definition],
    baseline: bool,
) -> tuple[tuple[DefinitionChange, ...], tuple[DefinitionCorrespondence, ...]]:
    prior = {item.id: item for item in before}
    matched: dict[DefinitionId, Definition] = {}
    for item in after:
        identity = item.baseline_definition_id if baseline else item.id
        if identity in prior:
            if identity in matched:
                raise ValueError("Retain only one direct copy for each baseline definition")
            matched[identity] = item
    remapping: dict[DefinitionReference, DefinitionReference] = {
        item.id: identity for identity, item in matched.items()
    }
    before_bodies = (
        comparable_shape_bodies(
            bodies={item.id: item.body for item in before},
            replacements={},
        )
        if baseline
        else {}
    )
    after_bodies = (
        comparable_shape_bodies(
            bodies={item.id: item.body for item in after},
            replacements=remapping,
        )
        if baseline
        else {}
    )
    changes: list[DefinitionChange] = []
    correspondences: list[DefinitionCorrespondence] = []
    for earlier in before:
        later = matched.get(earlier.id)
        if later is None:
            changes.append(
                DefinitionChange(kind=DefinitionChangeKind.REMOVE, before=(earlier,), after=()),
            )
            continue
        correspondences.append(DefinitionCorrespondence(before_id=earlier.id, after_id=later.id))
        equal = (
            _baseline_equivalent(
                original=earlier,
                copy=later,
                original_body=before_bodies[earlier.id],
                copied_body=after_bodies[later.id],
            )
            if baseline
            else earlier == later
        )
        if not equal:
            changes.append(definition_change(before=earlier, after=later))
    changes.extend(
        definition_change(before=None, after=item) for item in after if item.id not in remapping
    )
    return tuple(changes), tuple(correspondences)


def compare_candidates(
    *,
    before: Candidate | None,
    after: Candidate,
    before_pin: SnapshotReference | None,
    after_pin: SnapshotReference,
) -> ChangeSet:
    """Describe exact definition lineage and captured context changes."""
    baseline = before is not None and before.scope != after.scope
    if baseline and (before_pin is None or before_pin != after.baseline):
        raise ScopeMismatchError
    before_records = ()
    if before is not None:
        before_records = (
            tuple(before.content.definitions)
            if baseline
            else (*before.content.definitions, *before.content.retired_definitions)
        )
    changes, correspondences = _definition_deltas(
        before=before_records,
        after=(*after.content.definitions, *after.content.retired_definitions),
        baseline=baseline,
    )
    old_source = (
        {}
        if before is None
        else {item.proposal_id: item for item in before.content.source_alignments}
    )
    new_source = {item.proposal_id: item for item in after.content.source_alignments}
    old_reference = (
        {}
        if before is None
        else {item.definition_id: item for item in before.content.reference_dispositions}
    )
    match = {item.after_id: item.before_id for item in correspondences}
    new_reference = {
        match.get(item.definition_id, item.definition_id): item
        for item in after.content.reference_dispositions
    }
    source_changes = tuple(
        SourceAlignmentChange(before=old_source.get(key), after=new_source.get(key))
        for key in dict.fromkeys((*old_source, *new_source))
        if old_source.get(key) != new_source.get(key)
    )
    reference_changes = tuple(
        ReferenceDispositionChange(before=old_reference.get(key), after=new_reference.get(key))
        for key in dict.fromkeys((*old_reference, *new_reference))
        if old_reference.get(key) != new_reference.get(key)
    )
    comparison = ComparisonKind.INITIAL
    compatibility = Compatibility.INITIAL
    before_pack = None if before is None else before.reference_pack
    before_dependencies = () if before is None else before.dependencies
    if before is not None:
        comparison = ComparisonKind.BASELINE if baseline else ComparisonKind.REVISION
        if any(_breaking(change=item) for item in changes):
            compatibility = Compatibility.BREAKING
        elif (
            changes
            or source_changes
            or reference_changes
            or before_pack != after.reference_pack
            or before_dependencies != after.dependencies
        ):
            compatibility = Compatibility.UNDETERMINED
        else:
            compatibility = Compatibility.COMPATIBLE
    return ChangeSet(
        scope=after.scope,
        changes=changes,
        compatibility=compatibility,
        comparison=comparison,
        before=before_pin,
        after=after_pin,
        before_reference_pack=before_pack,
        after_reference_pack=after.reference_pack,
        before_dependencies=before_dependencies,
        after_dependencies=after.dependencies,
        correspondences=correspondences,
        source_alignment_changes=source_changes,
        reference_disposition_changes=reference_changes,
    )
