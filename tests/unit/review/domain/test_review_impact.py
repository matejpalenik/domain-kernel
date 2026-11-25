"""Keep review impact consistent with the captured changes."""

from __future__ import annotations

from domain_kernel import (
    DefinitionId,
    ProposalId,
)
from domain_kernel._shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    SourceAlignment,
    SourceAlignmentChange,
    SourceDisposition,
)
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.review.domain.models import (
    ReviewCase,
    ReviewImpact,
)


def test_mapping_only_impact_is_a_view_of_the_same_changes(proposal: ReviewCase) -> None:
    alignment = SourceAlignment(
        proposal_id=ProposalId(value="occurrence"),
        definition_id=DefinitionId(value="machine"),
        definition_revision=1,
        disposition=SourceDisposition.MAPPED,
        decision_id=None,
        rationale="The occurrence uses the same meaning.",
        context_fingerprint="inspected-context",
    )
    changes = ChangeSet(
        scope=proposal.scope,
        changes=(),
        compatibility=Compatibility.COMPATIBLE,
        comparison=ComparisonKind.PROPOSAL,
        source_alignment_changes=[SourceAlignmentChange(before=None, after=alignment)],
    )
    impact = ReviewImpact(changes=changes, workspace_revision=1, affected_case_ids=(proposal.id,))
    wire = record_bytes(value=changes)

    assert impact.definition_changes == ()
    assert impact.source_alignment_changes is changes.source_alignment_changes
    assert impact.reference_disposition_changes is changes.reference_disposition_changes
    assert record_bytes(value=impact.changes) == wire
    assert read_record(content=wire, expected=ChangeSet) == changes
