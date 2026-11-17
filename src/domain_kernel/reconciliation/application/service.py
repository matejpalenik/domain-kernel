"""Prepare both layers, their review cases, and the audit in one transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Invocation, OperationOutcome
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.reconciliation.application.matcher import reference_members
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.reconciliation.domain.identifiers.alignment_suggestion_id import (
    AlignmentSuggestionId,
)
from domain_kernel.reconciliation.domain.models import (
    Alignment,
    AlignmentLayer,
    AlignmentStatus,
    AlignmentSuggestion,
)
from domain_kernel.reference_packs.domain.contracts import MappingRelation, ObligationKind
from domain_kernel.review.application.reference_alignment import reviewed_dispositions
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import ReviewCase
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.changes import ReferenceDisposition
    from domain_kernel._shared.domain.definitions import Definition
    from domain_kernel.discovery.domain.models import DiscoveryDraft, Proposal
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.reconciliation.application.matcher import EvidenceBasedConceptMatcher
    from domain_kernel.reconciliation.application.ports import ReconciliationTransaction
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
        ReferenceDefinitionId,
    )
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId


@dataclass(frozen=True, kw_only=True)
class _Context:
    draft: DiscoveryDraft
    info: ModelInfo
    alignment_id: AlignmentId
    definitions: Sequence[Definition]

    @property
    def fingerprint(self) -> str:
        return hash_json(
            value=record_value(
                value=(
                    self.info.description,
                    self.info.reference_pack,
                    self.info.baseline,
                    self.info.dependencies,
                ),
            )
        ).value


@dataclass(frozen=True, kw_only=True)
class _SourceReview:
    suggestions: Sequence[AlignmentSuggestion]
    cases: Sequence[ReviewCase]
    unmatched: Sequence[ProposalId]


@dataclass(frozen=True, kw_only=True)
class _ReferenceReview:
    suggestions: Sequence[AlignmentSuggestion] = ()
    cases: Sequence[ReviewCase] = ()
    uncovered: Sequence[ReferenceDefinitionId] = ()


def _occurrence_fingerprint(*, context: _Context, proposal: Proposal) -> str:
    definition = proposal.definition
    return hash_json(
        value=record_value(
            value=(
                context.fingerprint,
                definition.name,
                definition.meaning,
                definition.body,
                definition.terminology,
                proposal.evidence,
            )
        )
    ).value


def _reference_fingerprint(*, context: _Context, local: Definition) -> str:
    return hash_json(value=record_value(value=(context.fingerprint, local))).value


def _reference_gaps(
    *, pack: ReferencePack, dispositions: Sequence[ReferenceDisposition]
) -> tuple[ReferenceDefinitionId, ...]:
    required = dict.fromkeys(
        identity
        for item in pack.obligations
        if item.required and item.kind is ObligationKind.COVERAGE
        for identity in item.reference_ids
    )
    covered = {
        item.alignment.reference_id
        for item in dispositions
        if item.alignment is not None
        and item.alignment.relation in (MappingRelation.EQUIVALENT, MappingRelation.NARROWER)
    }
    return tuple(identity for identity in required if identity not in covered)


@final
class Reconciliation:
    """Process a completed extraction independently from its inference provider."""

    def __init__(
        self, *, transaction: ReconciliationTransaction, matcher: EvidenceBasedConceptMatcher
    ) -> None:
        """Bind the scoped repositories and the host's lexical scorer."""
        self._transaction = transaction
        self._matcher = matcher

    async def propose(
        self,
        *,
        model: ModelInfo,
        actor: str,
        discovery_id: DiscoveryDraftId,
        idempotency_key: str | None,
    ) -> Alignment:
        """Atomically prepare the review queue for one immutable discovery draft."""
        require_exact(value=discovery_id, expected=DiscoveryDraftId, field="Discovery draft ID")
        scope = model.scope
        transaction = self._transaction
        invocation = Invocation.resolve(
            project_id=scope.project_id,
            model_id=scope.model_id,
            operation="propose_alignment",
            actor=actor,
            key=idempotency_key,
            intent=discovery_id.value,
        )
        async with transaction.begin():
            claim = await transaction.operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "alignment":
                    raise StaleStateError(message="Inspect the stored alignment outcome.")
                return await transaction.reconciliation.get(
                    scope=scope, alignment_id=AlignmentId(value=claim.resource_id)
                )
            alignment = await transaction.reconciliation.for_draft(
                scope=scope, discovery_id=discovery_id
            )
            if alignment is None:
                alignment = await self._prepare(model=model, actor=actor, discovery_id=discovery_id)
            await transaction.operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(resource_kind="alignment", resource_id=alignment.id.value),
            )
            return alignment

    async def _prepare(
        self, *, model: ModelInfo, actor: str, discovery_id: DiscoveryDraftId
    ) -> Alignment:
        transaction = self._transaction
        scope = model.scope
        draft = await transaction.extraction.draft(identifier=discovery_id, scope=scope)
        current = await transaction.models.get(project_id=scope.project_id, name=model.name)
        pack = await transaction.packs.get(scope=scope)
        if current.reference_pack != (None if pack is None else pack.pin):
            raise StaleStateError(message="Reopen the exact selected reference pack.")
        context = _Context(
            draft=draft,
            info=current,
            alignment_id=AlignmentId(value=uuid4().hex),
            definitions=await transaction.definitions.active(scope=scope),
        )
        sources = self._source_review(context=context)
        references = (
            _ReferenceReview()
            if pack is None
            else await self._reference_review(context=context, pack=pack)
        )
        alignment = Alignment(
            id=context.alignment_id,
            scope=scope,
            discovery_id=discovery_id,
            reference_pack=current.reference_pack,
            version=1,
            status=AlignmentStatus.PROPOSED,
            suggestions=(*sources.suggestions, *references.suggestions),
            unmatched_proposal_ids=sources.unmatched,
            uncovered_reference_ids=references.uncovered,
        ).mark_prepared(expected_version=1)
        await transaction.revisions.advance(scope=scope, expected_revision=current.revision)
        await transaction.reconciliation.add(alignment=alignment)
        for case in (*sources.cases, *references.cases):
            await transaction.reviews.add(case=case)
        await transaction.audit.append(
            record=AuditRecord(
                id=AuditId(value=uuid4().hex),
                project_id=scope.project_id,
                model_id=scope.model_id,
                action=AuditAction.PROPOSE_ALIGNMENT,
                outcome=AuditOutcome.SUCCEEDED,
                actor=actor,
                recorded_at=datetime.now(tz=UTC),
                reason="Prepare evidence-backed source and reference review cases.",
                before=(
                    AuditResource(
                        resource_id=draft.id,
                        revision=None,
                        content_hash=hash_json(value=record_value(value=draft)),
                    ),
                ),
                after=(
                    AuditResource(
                        resource_id=alignment.id,
                        revision=alignment.version,
                        content_hash=hash_json(value=record_value(value=alignment)),
                    ),
                ),
            )
        )
        return alignment

    def _source_review(self, *, context: _Context) -> _SourceReview:
        draft = context.draft
        suggestions: list[AlignmentSuggestion] = []
        cases: list[ReviewCase] = []
        unmatched: list[ProposalId] = []
        for proposal in draft.proposals:
            candidates = self._matcher.source(
                proposed=proposal.definition, active=context.definitions
            )
            occurrence = _occurrence_fingerprint(context=context, proposal=proposal)
            suggestions.extend(
                AlignmentSuggestion(
                    id=AlignmentSuggestionId(value=uuid4().hex),
                    scope=draft.scope,
                    layer=AlignmentLayer.SOURCE_TO_MODEL,
                    proposal_ids=(proposal.id,),
                    definition_id=candidate.target.id,
                    definition_revision=candidate.target.revision,
                    reference_id=None,
                    relation=None,
                    evidence=proposal.evidence,
                    reason=candidate.reason,
                    context_fingerprint=hash_json(
                        value=record_value(value=(occurrence, candidate.target)),
                    ).value,
                )
                for candidate in candidates
            )
            if not candidates:
                unmatched.append(proposal.id)
            cases.append(
                ReviewCase(
                    id=ReviewCaseId(value=uuid4().hex),
                    scope=draft.scope,
                    kind=CaseKind.SOURCE_ALIGNMENT,
                    status=CaseStatus.PENDING,
                    version=1,
                    definitions=(proposal.definition, *(item.target for item in candidates)),
                    reason=(
                        "Review the exact source occurrence against its local meaning candidates."
                        if candidates
                        else "Review a source occurrence without a local meaning candidate."
                    ),
                    run_id=draft.run_id,
                    reconciliation_id=context.alignment_id,
                    proposal_ids=(proposal.id,),
                    evidence=proposal.evidence,
                    context_fingerprint=occurrence,
                )
            )
        return _SourceReview(suggestions=suggestions, cases=cases, unmatched=unmatched)

    async def _reference_review(
        self, *, context: _Context, pack: ReferencePack
    ) -> _ReferenceReview:
        members = reference_members(pack=pack)
        suggestions: list[AlignmentSuggestion] = []
        cases: list[ReviewCase] = []
        dispositions: list[ReferenceDisposition] = []
        reviewed = await reviewed_dispositions(
            repository=self._transaction.reviews, definitions=context.definitions, pack=pack.pin
        )
        for local in context.definitions:
            inspected = reviewed.get(local.id)
            prior = None if inspected is None else inspected.choice
            fingerprint = _reference_fingerprint(context=context, local=local)
            if inspected is not None and inspected.context_fingerprint in (None, fingerprint):
                prior = inspected.choice
                dispositions.append(prior)
                if prior.alignment is not None:
                    suggestions.append(
                        AlignmentSuggestion(
                            id=AlignmentSuggestionId(value=uuid4().hex),
                            scope=local.scope,
                            layer=AlignmentLayer.MODEL_TO_REFERENCE,
                            proposal_ids=(),
                            definition_id=local.id,
                            definition_revision=local.revision,
                            reference_id=prior.alignment.reference_id,
                            relation=prior.alignment.relation,
                            evidence=local.evidence,
                            reason=prior.rationale,
                            context_fingerprint=fingerprint,
                            reused_decision_id=prior.decision_id,
                        )
                    )
                continue
            candidates = self._matcher.reference(local=local, members=members)
            if not candidates and prior is None:
                continue
            suggestions.extend(
                AlignmentSuggestion(
                    id=AlignmentSuggestionId(value=uuid4().hex),
                    scope=local.scope,
                    layer=AlignmentLayer.MODEL_TO_REFERENCE,
                    proposal_ids=(),
                    definition_id=local.id,
                    definition_revision=local.revision,
                    reference_id=item.target.id,
                    relation=None,
                    evidence=local.evidence,
                    reason=item.reason,
                    context_fingerprint=fingerprint,
                )
                for item in candidates
            )
            cases.append(
                ReviewCase(
                    id=ReviewCaseId(value=uuid4().hex),
                    scope=local.scope,
                    kind=CaseKind.REFERENCE_ALIGNMENT,
                    status=CaseStatus.PENDING,
                    version=1,
                    definitions=(local,),
                    reason=(
                        "Review the earlier reference choice against the updated model context."
                        if prior is not None
                        else "Compare the local meaning with candidates in the selected pack."
                    ),
                    reference_pack=pack.pin,
                    reference_before=prior,
                    run_id=context.draft.run_id,
                    reconciliation_id=context.alignment_id,
                    evidence=local.evidence,
                    context_fingerprint=fingerprint,
                )
            )
        return _ReferenceReview(
            suggestions=suggestions,
            cases=cases,
            uncovered=_reference_gaps(pack=pack, dispositions=dispositions),
        )
