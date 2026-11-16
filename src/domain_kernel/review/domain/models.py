"""Immutable manual review state and the effects of an inspected leaf decision."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.definitions import Definition
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.review.domain.decisions import Accept, EditDefinition, Reject
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import Issue, ModelScope
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from domain_kernel._shared.domain.authoring import ModelChangePlan
    from domain_kernel._shared.domain.changes import (
        ChangeSet,
        Compatibility,
        DefinitionChange,
        ReferenceDispositionChange,
        SourceAlignmentChange,
    )
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId


@dataclass(frozen=True, kw_only=True)
class CaseDecision:
    """An explicit choice bound to an inspected case version."""

    case_id: ReviewCaseId
    expected_version: int
    decision: ReviewAction

    def __post_init__(self) -> None:
        """Validate the nominal case identity and version."""
        require_exact(value=self.case_id, expected=ReviewCaseId, field="Case ID")
        require_exact(value=self.expected_version, expected=int, field="Case version")
        if self.expected_version < 1:
            raise ValueError("Case versions are positive")
        if type(self.decision) not in (Accept, EditDefinition, Reject):
            raise TypeError("Use a supported manual review action")


@dataclass(frozen=True, kw_only=True)
class ReviewCase:
    """An immutable inspected case for manual definition authoring."""

    id: ReviewCaseId
    scope: ModelScope
    kind: CaseKind
    status: CaseStatus
    version: int
    definitions: Sequence[Definition]
    reason: str

    change_plan: ModelChangePlan | None = None
    members: Sequence[CaseDecision] = ()
    generated_member_case_ids: Sequence[ReviewCaseId] = ()
    grouped_by_case_id: ReviewCaseId | None = None
    guarded_workspace_revision: int | None = None

    def __post_init__(self) -> None:
        """Capture case identity, reason and the inspected definitions."""
        require_exact(value=self.id, expected=ReviewCaseId, field="Review case identity")
        require_exact(value=self.scope, expected=ModelScope, field="Review scope")
        require_exact(value=self.kind, expected=CaseKind, field="Review case kind")
        require_exact(value=self.status, expected=CaseStatus, field="Review case status")
        require_exact(value=self.version, expected=int, field="Review case version")
        require_text(value=self.reason, field="Proposal reason")
        if self.version < 1:
            raise ValueError("Review case version must be positive")
        object.__setattr__(
            self,
            "definitions",
            snapshot_sequence(
                items=self.definitions, item_type=Definition, field="Review definitions"
            ),
        )
        self._capture_members()

    def _capture_members(self) -> None:
        members = snapshot_sequence(
            items=self.members, item_type=CaseDecision, field="Group members"
        )
        generated = snapshot_sequence(
            items=self.generated_member_case_ids,
            item_type=ReviewCaseId,
            field="Generated members",
        )
        member_ids = {member.case_id for member in members}
        if self.kind is CaseKind.CHANGE_SET:
            if not members or len(member_ids) != len(members) or not set(generated) <= member_ids:
                raise ValueError("Use one explicit decision per distinct coordinated member")
            if self.guarded_workspace_revision is None or self.grouped_by_case_id is not None:
                raise ValueError("A group requires its own inspected workspace guard")
            if self.change_plan is not None and self.change_plan.scope != self.scope:
                raise ValueError("The plan must belong to the group's workspace")
        elif (
            members
            or generated
            or self.change_plan is not None
            or self.guarded_workspace_revision is not None
        ):
            raise ValueError("Only coordinated cases can own grouped review metadata")
        if len(set(generated)) != len(generated):
            raise ValueError("Generated member IDs must be distinct")
        if self.grouped_by_case_id is not None:
            require_exact(value=self.grouped_by_case_id, expected=ReviewCaseId, field="Parent case")
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "generated_member_case_ids", generated)

    def _preview(self, *, decision: ReviewAction) -> tuple[Definition, ...]:
        if self.grouped_by_case_id is not None:
            raise InvalidDecisionError(message="Inspect and decide the coordinating parent case")
        if self.status is not CaseStatus.PENDING:
            raise InvalidDecisionError(message="Open a pending case before choosing a decision")
        if self.kind is not CaseKind.PROPOSAL or len(self.definitions) != 1:
            raise InvalidDecisionError(message="Use a manual definition proposal for this decision")
        if type(decision) is Reject:
            return ()
        proposed = self.definitions[0]
        if proposed.scope != self.scope or proposed.status is not DefinitionStatus.PROPOSED:
            raise InvalidDecisionError(message="Use the proposed definition from this case")
        if type(decision) is EditDefinition:
            if (
                decision.definition_id != proposed.id
                or decision.name != proposed.name
                or decision.body.kind is not proposed.body.kind
            ):
                raise InvalidDecisionError(message="Keep the proposed identity, name and kind")
            proposed = replace(
                proposed,
                display_name=decision.display_name,
                meaning=decision.meaning,
                body=decision.body,
                aliases=decision.aliases,
                terminology=decision.terminology,
            )
        elif type(decision) is not Accept:
            raise InvalidDecisionError(message="Choose an applicable manual review action")
        return (replace(proposed, status=DefinitionStatus.APPROVED),)

    def _decide(
        self, *, decision: ReviewAction, actor: str, expected_version: int, now: datetime
    ) -> ReviewCase:
        require_text(value=actor, field="Actor")
        require_exact(value=expected_version, expected=int, field="Expected case version")
        if expected_version != self.version:
            raise StaleStateError
        if now.utcoffset() is None:
            raise ValueError("Decision time must include a time zone")
        _ = self._preview(decision=decision)
        return replace(self, status=CaseStatus.RESOLVED, version=self.version + 1)


def preview_case(*, case: ReviewCase, decision: ReviewAction) -> tuple[Definition, ...]:
    """Use the case-local effect policy inside the review service."""
    return case._preview(decision=decision)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001


def resolve_case(
    *,
    case: ReviewCase,
    decision: ReviewAction,
    actor: str,
    expected_version: int,
    now: datetime,
) -> ReviewCase:
    """Apply the case-local transition after service-supplied current state checks."""
    return case._decide(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        decision=decision,
        actor=actor,
        expected_version=expected_version,
        now=now,
    )


@dataclass(frozen=True, kw_only=True)
class ReviewImpact:
    """Read-only prospective effects scoped to one inspected workspace revision."""

    changes: ChangeSet
    workspace_revision: int
    affected_case_ids: Sequence[ReviewCaseId]
    invalidated_decision_ids: Sequence[DecisionId] = ()
    blockers: Sequence[Issue] = ()

    def __post_init__(self) -> None:
        """Detach prospective changes and diagnostic sequences."""
        object.__setattr__(
            self,
            "affected_case_ids",
            snapshot_sequence(
                items=self.affected_case_ids,
                item_type=ReviewCaseId,
                field="Affected review cases",
            ),
        )
        object.__setattr__(
            self,
            "invalidated_decision_ids",
            snapshot_sequence(
                items=self.invalidated_decision_ids,
                item_type=DecisionId,
                field="Invalidated decisions",
            ),
        )
        object.__setattr__(
            self,
            "blockers",
            snapshot_sequence(items=self.blockers, item_type=Issue, field="Blockers"),
        )

    @property
    def definition_changes(self) -> Sequence[DefinitionChange]:
        """Return the changes from the shared change set."""
        return self.changes.changes

    @property
    def source_alignment_changes(self) -> Sequence[SourceAlignmentChange]:
        """Return source effects from the shared change set."""
        return self.changes.source_alignment_changes

    @property
    def reference_disposition_changes(self) -> Sequence[ReferenceDispositionChange]:
        """Return reference effects from the shared change set."""
        return self.changes.reference_disposition_changes

    @property
    def compatibility(self) -> Compatibility:
        """Return the shared contract compatibility assessment."""
        return self.changes.compatibility


@dataclass(frozen=True, kw_only=True)
class ReviewReceipt:
    """Identity and workspace revision of a committed review."""

    scope: ModelScope
    case_id: ReviewCaseId
    case_version: int
    decision_id: DecisionId
    workspace_revision: int
    member_decision_ids: tuple[DecisionId, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DecisionRecord:
    """Exact actor, inspected case version and committed effects for one decision."""

    id: DecisionId
    scope: ModelScope
    case_id: ReviewCaseId
    case_version: int
    action: ReviewAction
    actor: str
    recorded_at: datetime
    applied_changes: ChangeSet
    proposal_ids: tuple[ProposalId, ...] = ()
    supersedes_decision_id: DecisionId | None = None
    change_plan: ModelChangePlan | None = None
    group_decision_id: DecisionId | None = None
    member_decision_ids: tuple[DecisionId, ...] = ()
    generated_member_case_ids: tuple[ReviewCaseId, ...] = ()
    released_case_ids: tuple[ReviewCaseId, ...] = ()
