"""Compare immutable same-model snapshots without performing I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel._shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    DefinitionChange,
    DefinitionCorrespondence,
    ReferenceDispositionChange,
    SourceAlignmentChange,
)
from domain_kernel._shared.domain.lifecycle import definition_change
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.shared.errors import ScopeMismatchError

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.shared.contracts import SnapshotReference


def compare_candidates(
    *,
    before: Candidate | None,
    after: Candidate,
    before_pin: SnapshotReference | None,
    after_pin: SnapshotReference,
) -> ChangeSet:
    """Produce exact pins, content differences and compatibility of one pair."""
    if before is not None and before.scope != after.scope:
        raise ScopeMismatchError
    before_records = (
        {}
        if before is None
        else {
            value.id: value
            for value in (*before.content.definitions, *before.content.retired_definitions)
        }
    )
    after_records = {
        value.id: value
        for value in (*after.content.definitions, *after.content.retired_definitions)
    }
    changes: list[DefinitionChange] = []
    for identifier in dict.fromkeys((*before_records, *after_records)):
        earlier = before_records.get(identifier)
        later = after_records.get(identifier)
        if earlier == later:
            continue
        if later is not None:
            changes.append(definition_change(before=earlier, after=later))
        elif earlier is not None:
            changes.append(
                DefinitionChange(
                    kind=DefinitionChangeKind.REMOVE,
                    before=(earlier,),
                    after=(),
                )
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
    new_reference = {item.definition_id: item for item in after.content.reference_dispositions}
    compatibility = Compatibility.INITIAL
    if before is not None:
        compatibility = Compatibility.UNDETERMINED if changes else Compatibility.COMPATIBLE
    return ChangeSet(
        scope=after.scope,
        changes=changes,
        compatibility=compatibility,
        comparison=ComparisonKind.INITIAL if before is None else ComparisonKind.REVISION,
        before=before_pin,
        after=after_pin,
        before_reference_pack=None if before is None else before.reference_pack,
        after_reference_pack=after.reference_pack,
        before_dependencies=() if before is None else before.dependencies,
        after_dependencies=after.dependencies,
        correspondences=tuple(
            DefinitionCorrespondence(before_id=identifier, after_id=identifier)
            for identifier in before_records
            if identifier in after_records
        ),
        source_alignment_changes=tuple(
            SourceAlignmentChange(before=old_source.get(key), after=new_source.get(key))
            for key in dict.fromkeys((*old_source, *new_source))
            if old_source.get(key) != new_source.get(key)
        ),
        reference_disposition_changes=tuple(
            ReferenceDispositionChange(before=old_reference.get(key), after=new_reference.get(key))
            for key in dict.fromkeys((*old_reference, *new_reference))
            if old_reference.get(key) != new_reference.get(key)
        ),
    )
