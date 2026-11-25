"""Prepare both layers, their review cases, and the audit in one transaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.schema_policy import SCHEMA_V23
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.reconciliation.application.matcher import reference_members
from domain_kernel.reconciliation.application.ontology_shortlist import OntologyShortlist
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
from domain_kernel.review.application.source_review import source_decisions
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import ReviewCase
from domain_kernel.review.domain.occurrences import effective_occurrences
from domain_kernel.shared.application.persistence import Invocation, OperationOutcome
from domain_kernel.shared.domain.codecs.record_encoding import record_value
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.discovery.domain.models import DiscoveryDraft, Proposal
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.reconciliation.application.matcher import EvidenceBasedConceptMatcher
    from domain_kernel.reconciliation.application.ports import ReconciliationTransaction
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
        ReferenceDefinitionId,
    )
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.value_objects.reference_disposition import ReferenceDisposition
    from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment


def _schema_case_key(*, case: ReviewCase) -> tuple[CaseKind, str] | None:
    if case.kind is CaseKind.QUESTION and case.question is not None:
        return case.kind, case.question.id.value
    if case.kind in (CaseKind.SOURCE_ALIGNMENT, CaseKind.REFERENCE_ALIGNMENT) and case.definitions:
        return case.kind, case.definitions[0].id.value
    return None


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
        self,
        *,
        transaction: ReconciliationTransaction,
        matcher: EvidenceBasedConceptMatcher,
        ontology_shortlist: bool = False,
    ) -> None:
        """Bind the scoped repositories and the host's lexical scorer."""
        self._transaction = transaction
        self._matcher = matcher
        RuntimeTypeValidation.require_exact(
            value=ontology_shortlist, expected=bool, field="Ontology shortlist"
        )
        self._shortlist_profile = "ontology-shortlist-v1" if ontology_shortlist else None

    async def propose(
        self,
        *,
        model: ModelInfo,
        actor: str,
        discovery_id: DiscoveryDraftId,
        idempotency_key: str | None,
    ) -> Alignment:
        """Atomically prepare the review queue for one immutable discovery draft."""
        RuntimeTypeValidation.require_exact(
            value=discovery_id, expected=DiscoveryDraftId, field="Discovery draft ID"
        )
        scope = model.scope
        transaction = self._transaction
        invocation = Invocation.resolve(
            project_id=scope.project_id,
            model_id=scope.model_id,
            operation="propose_alignment",
            actor=actor,
            key=idempotency_key,
            intent=(discovery_id.value, self._shortlist_profile)
            if self._shortlist_profile
            else discovery_id.value,
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
            elif alignment.reference_shortlist_profile != self._shortlist_profile:
                raise StaleStateError(
                    message="Use a fresh discovery draft for a different shortlist policy."
                )
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
        if (
            draft.provenance.extractor_version == SCHEMA_V23
            and current.reference_pack != draft.context.reference_pack
        ):
            raise StaleStateError(message="Review against the captured reference pack.")
        context = _Context(
            draft=draft,
            info=current,
            alignment_id=AlignmentId(value=uuid4().hex),
            definitions=await transaction.definitions.active(scope=scope),
        )
        previous = effective_occurrences(
            decisions=await source_decisions(repository=transaction.reviews, scope=scope),
        )
        sources = self._source_review(context=context, previous=tuple(previous.values()))
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
            suggestions=(
                *sources.suggestions,
                *references.suggestions,
                *(
                    self._schema_reference_suggestions(context=context, pack=pack)
                    if pack is not None and draft.schema_modeled
                    else ()
                ),
            ),
            unmatched_proposal_ids=sources.unmatched,
            uncovered_reference_ids=references.uncovered,
            reference_shortlist_profile=self._shortlist_profile,
        ).mark_prepared(expected_version=1)
        await transaction.revisions.advance(scope=scope, expected_revision=current.revision)
        await transaction.reconciliation.add(alignment=alignment)
        cases = (
            *sources.cases,
            *references.cases,
            *(
                ReviewCase(
                    id=ReviewCaseId(value=uuid4().hex),
                    scope=scope,
                    kind=CaseKind.QUESTION,
                    status=CaseStatus.PENDING,
                    version=1,
                    definitions=(),
                    reason="Clarify the applicable meaning or bound before proposing it.",
                    run_id=draft.run_id,
                    reconciliation_id=alignment.id,
                    question=question,
                    evidence=question.evidence,
                )
                for question in draft.schema_questions
            ),
        )
        await self._store_cases(context=context, cases=cases)
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

    async def _store_cases(self, *, context: _Context, cases: Sequence[ReviewCase]) -> None:
        repository = self._transaction.reviews
        draft = context.draft
        earlier: dict[tuple[CaseKind, str], ReviewCase] = {}
        if draft.schema_modeled:
            cursor = None
            while True:
                page = await repository.list(
                    scope=draft.scope,
                    kind=None,
                    status=CaseStatus.PENDING,
                    limit=100,
                    cursor=cursor,
                    run_id=draft.run_id,
                )
                for case in page.items:
                    key = _schema_case_key(case=case)
                    if key is not None:
                        earlier[key] = case
                cursor = page.next_cursor
                if cursor is None:
                    break
        for case in cases:
            key = _schema_case_key(case=case)
            previous = earlier.get(key) if key is not None else None
            if previous is None:
                await repository.add(case=case)
            else:
                await repository.save(
                    case=replace(case, id=previous.id, version=previous.version + 1),
                    expected_version=previous.version,
                )

    def _schema_reference_suggestions(
        self, *, context: _Context, pack: ReferencePack
    ) -> tuple[AlignmentSuggestion, ...]:
        members = reference_members(pack=pack)
        if context.draft.provenance.extractor_version == SCHEMA_V23:
            return self._evidenced_reference_suggestions(
                context=context, pack=pack, member_ids={item.id for item in members}
            )
        return tuple(
            AlignmentSuggestion(
                id=AlignmentSuggestionId(value=uuid4().hex),
                scope=context.draft.scope,
                layer=AlignmentLayer.MODEL_TO_REFERENCE,
                proposal_ids=(proposal.id,),
                definition_id=proposal.definition.id,
                definition_revision=proposal.definition.revision,
                reference_id=candidate.target.id,
                relation=None,
                evidence=proposal.evidence,
                reason=candidate.reason,
                context_fingerprint=_reference_fingerprint(
                    context=context, local=proposal.definition
                ),
            )
            for proposal in context.draft.proposals
            for candidate in self._matcher.reference(
                local=proposal.definition, members=members, endpoint_alignments={}
            )
        )

    def _evidenced_reference_suggestions(
        self,
        *,
        context: _Context,
        pack: ReferencePack,
        member_ids: set[ReferenceDefinitionId],
    ) -> tuple[AlignmentSuggestion, ...]:
        if context.draft.context.reference_pack != pack.pin or any(
            hint.reference not in member_ids for hint in context.draft.schema_mappings
        ):
            raise StaleStateError(message="Review suggestions against the captured reference pack.")
        proposals = {item.definition.id: item for item in context.draft.proposals}
        result: list[AlignmentSuggestion] = []
        for hint in context.draft.schema_mappings:
            proposal = proposals[hint.definition]
            result.append(
                AlignmentSuggestion(
                    id=AlignmentSuggestionId(value=uuid4().hex),
                    scope=context.draft.scope,
                    layer=AlignmentLayer.MODEL_TO_REFERENCE,
                    proposal_ids=(proposal.id,),
                    definition_id=proposal.definition.id,
                    definition_revision=proposal.definition.revision,
                    reference_id=hint.reference,
                    relation=None,
                    evidence=proposal.evidence,
                    reason=f"Suggested {hint.relation.value}: {hint.reason}",
                    context_fingerprint=_reference_fingerprint(
                        context=context, local=proposal.definition
                    ),
                )
            )
        return tuple(result)

    def _source_review(
        self,
        *,
        context: _Context,
        previous: Sequence[SourceAlignment],
    ) -> _SourceReview:
        draft = context.draft
        suggestions: list[AlignmentSuggestion] = []
        cases: list[ReviewCase] = []
        unmatched: list[ProposalId] = []
        active = {item.id: item for item in context.definitions}
        endpoint_ids = {
            item.relationship_id: {
                endpoint.definition_id
                for endpoint in (item.source, item.target)
                if endpoint is not None
            }
            for item in draft.relationship_bindings
            if item.relationship_id is not None
        }
        approved = {item.id: item for item in draft.context.approved_definitions}
        for proposal in draft.proposals:
            if draft.schema_modeled and isinstance(
                body := proposal.definition.body, RelationshipDefinition
            ):
                endpoint_ids[proposal.definition.id] = {
                    item.id
                    for item in approved.values()
                    if item.id in (body.source_concept_id, body.target_concept_id)
                }
            occurrence = _occurrence_fingerprint(context=context, proposal=proposal)
            reviewed = tuple(
                item
                for item in previous
                if item.disposition is SourceDisposition.MAPPED
                and item.context_fingerprint == occurrence
                and item.evidence == proposal.evidence
                and item.definition_id is not None
                and (target := active.get(item.definition_id)) is not None
                and item.definition_revision == target.revision
            )
            reused_targets = {item.definition_id for item in reviewed}
            if len(reused_targets) == 1 and self._reuse_source(
                proposal=proposal,
                reviewed=reviewed[0],
                suggestions=suggestions,
            ):
                continue
            candidates = self._matcher.source(
                proposed=proposal.definition,
                active=context.definitions,
            )
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
                    schema_review=proposal.schema_review,
                    context_fingerprint=occurrence,
                    relationship_endpoint_definitions=tuple(
                        approved[identity]
                        for identity in approved
                        if identity in endpoint_ids.get(proposal.definition.id, ())
                    ),
                )
            )
        return _SourceReview(suggestions=suggestions, cases=cases, unmatched=unmatched)

    @staticmethod
    def _reuse_source(
        *,
        proposal: Proposal,
        reviewed: SourceAlignment,
        suggestions: list[AlignmentSuggestion],
    ) -> bool:
        if (
            reviewed.definition_id is None
            or reviewed.definition_revision is None
            or reviewed.decision_id is None
        ):
            return False
        suggestions.append(
            AlignmentSuggestion(
                id=AlignmentSuggestionId(value=uuid4().hex),
                scope=proposal.scope,
                layer=AlignmentLayer.SOURCE_TO_MODEL,
                proposal_ids=(proposal.id,),
                definition_id=reviewed.definition_id,
                definition_revision=reviewed.definition_revision,
                reference_id=None,
                relation=None,
                evidence=proposal.evidence,
                reason=reviewed.rationale,
                context_fingerprint=reviewed.context_fingerprint,
                reused_decision_id=reviewed.decision_id,
            )
        )
        return True

    async def _reference_review(
        self, *, context: _Context, pack: ReferencePack
    ) -> _ReferenceReview:
        members = reference_members(pack=pack)
        ontology = (
            OntologyShortlist(pack=pack, members=members) if self._shortlist_profile else None
        )
        suggestions: list[AlignmentSuggestion] = []
        cases: list[ReviewCase] = []
        dispositions: list[ReferenceDisposition] = []
        reviewed = await reviewed_dispositions(
            repository=self._transaction.reviews, definitions=context.definitions, pack=pack.pin
        )
        endpoint_alignments = {
            local.id: alignment.reference_id
            for local in context.definitions
            if local.kind is DefinitionKind.CONCEPT
            and (item := reviewed.get(local.id)) is not None
            and item.context_fingerprint == _reference_fingerprint(context=context, local=local)
            and (alignment := item.choice.alignment) is not None
            and alignment.relation is MappingRelation.EQUIVALENT
        }
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
            candidates = self._matcher.reference(
                local=local,
                members=members,
                endpoint_alignments=endpoint_alignments,
                ontology=ontology,
            )
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
