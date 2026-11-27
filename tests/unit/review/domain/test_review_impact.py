"""Keep review impact consistent with the captured changes."""

from __future__ import annotations

from domain_kernel import (
    DefinitionId,
    ProposalId,
)
from domain_kernel.review.domain.models import (
    ReviewCase,
    ReviewImpact,
)
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.enums.comparison_kind import ComparisonKind
from domain_kernel.shared.domain.enums.compatibility import Compatibility
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.value_objects.change_set import ChangeSet
from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment
from domain_kernel.shared.domain.value_objects.source_alignment_change import SourceAlignmentChange


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
    wire = RecordCodec.encode(value=changes)

    assert impact.definition_changes == ()
    assert impact.source_alignment_changes is changes.source_alignment_changes
    assert impact.reference_disposition_changes is changes.reference_disposition_changes
    assert RecordCodec.encode(value=impact.changes) == wire
    assert RecordCodec.decode(content=wire, expected=ChangeSet) == changes
