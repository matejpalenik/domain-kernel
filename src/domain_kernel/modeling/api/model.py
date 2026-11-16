"""Public handle for an independently managed model workspace."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Never, final

from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    DefinitionBody,
    RelationshipDefinition,
    UnitDefinition,
)
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import DefinitionKindMismatchError
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.application.manual_review import ManualReview
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.shared.validation import is_non_string_sequence, require_exact

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.persistence import UnitOfWorkFactory
    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel._shared.domain.model_values import Terminology
    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import (
        DecisionRecord,
        ReviewCase,
        ReviewImpact,
        ReviewReceipt,
    )
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@final
class Model:
    """Read the model's captured metadata and attributed history."""

    def __init__(
        self,
        *,
        info: ModelInfo,
        resources: UnitOfWorkFactory[CatalogTransaction],
    ) -> None:
        """Bind a detached metadata snapshot to the client's resource factory."""
        self._info = info
        self._resources = resources

    @property
    def info(self) -> ModelInfo:
        """Return the loaded metadata without querying the workspace."""
        return self._info

    @property
    def scope(self) -> ModelScope:
        """Return the stable project and model IDs."""
        return self._info.scope

    async def get_audit_history(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[AuditRecord]:
        """Inspect durable events for this model."""
        async with self._resources() as transaction, transaction.begin():
            return await transaction.audit.list(
                project_id=self.scope.project_id,
                model_id=self.scope.model_id,
                limit=limit,
                cursor=cursor,
            )

    @asynccontextmanager
    async def _open_review(self) -> AsyncGenerator[ReviewTransaction]:
        async with self._resources() as transaction:
            if not isinstance(transaction, ReviewTransaction):
                raise MissingCapabilityError(
                    message="Configure persistence with manual review support"
                )
            yield transaction

    def _review_service(self, *, transaction: ReviewTransaction) -> ManualReview:
        return ManualReview(
            scope=self.scope,
            definitions=transaction.definitions,
            reviews=transaction.reviews,
            audit=transaction.audit,
            operations=transaction.operations,
            revisions=transaction.revisions,
            transaction=transaction,
        )

    async def propose_definition(  # noqa: PLR0913 - The SDK exposes exact authoring inputs.
        self,
        *,
        actor: str,
        display_name: str | None = None,
        name: str | None = None,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Propose an authored definition for review and retain its reserved name."""
        if not is_non_string_sequence(evidence) or evidence:
            raise ValueError("Manual authoring currently accepts an empty evidence sequence")
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).propose(
                actor=actor,
                name=name,
                display_name=display_name,
                meaning=meaning,
                body=body,
                aliases=aliases,
                terminology=terminology,
                reason=reason,
                idempotency_key=idempotency_key,
            )

    async def preview_changes(self, *, case: ReviewCase, decision: ReviewAction) -> ReviewImpact:
        """Inspect prospective effects from the exact supplied case."""
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).preview(
                case=case, decision=decision
            )

    async def decide_review(
        self,
        *,
        case: ReviewCase,
        decision: ReviewAction,
        actor: str,
        idempotency_key: str | None = None,
    ) -> ReviewReceipt:
        """Submit one host-attributed decision for the inspected case."""
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).decide(
                case=case,
                decision=decision,
                actor=actor,
                idempotency_key=idempotency_key,
            )

    async def get_review_case(self, *, case_id: ReviewCaseId) -> ReviewCase:
        """Open an exact review case in this model."""
        require_exact(value=case_id, expected=ReviewCaseId, field="Review case ID")
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.reviews.get(scope=self.scope, case_id=case_id, version=None)

    async def list_review_cases(  # noqa: PLR0913 - Explicit query filters bind continuation.
        self,
        *,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
        kind: CaseKind | None = None,
        status: CaseStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ReviewCase]:
        """Page through inspected review cases in this model."""
        if kind is not None:
            require_exact(value=kind, expected=CaseKind, field="Case kind")
        if status is not None:
            require_exact(value=status, expected=CaseStatus, field="Case status")
        if run_id is not None or reconciliation_id is not None:
            if cursor is not None:
                raise ValueError("Use a cursor returned by the same review case query")
            return Page(items=())
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.reviews.list(
                scope=self.scope,
                kind=kind,
                status=status,
                limit=limit,
                cursor=cursor,
            )

    async def get_review_history(
        self,
        *,
        case_id: ReviewCaseId,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[DecisionRecord]:
        """Inspect committed decisions for the selected case."""
        require_exact(value=case_id, expected=ReviewCaseId, field="Review case ID")
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.reviews.history(
                scope=self.scope,
                case_id=case_id,
                limit=limit,
                cursor=cursor,
            )

    async def get_definition(
        self,
        *,
        name: str | None = None,
        definition_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition:
        """Find an exact materialized definition, optionally at a historical revision."""
        if (name is None) == (definition_id is None):
            raise ValueError("Supply exactly one definition name or ID")
        if name is not None:
            require_lookup_name(name=name)
        else:
            require_exact(value=definition_id, expected=DefinitionId, field="Definition ID")
        if revision is not None:
            require_exact(value=revision, expected=int, field="Definition revision")
            if revision < 1:
                raise ValueError("Definition revision must be positive")
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.definitions.get(
                scope=self.scope,
                name=name,
                definition_id=definition_id,
                revision=revision,
            )

    async def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Concept:
        """Return an inspected concept with its local attribute and key reads."""
        value = await self.get_definition(name=name, definition_id=concept_id, revision=revision)
        concept = _view(value=value, body_type=ConceptDefinition, view_type=Concept)
        if not isinstance(concept, Concept):
            raise DefinitionKindMismatchError
        return concept

    async def get_relationship(
        self,
        *,
        name: str | None = None,
        relationship_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[RelationshipDefinition]:
        """Return an exact relationship revision."""
        value = await self.get_definition(
            name=name, definition_id=relationship_id, revision=revision
        )
        return _view(
            value=value,
            body_type=RelationshipDefinition,
            view_type=Definition[RelationshipDefinition],
        )

    async def get_unit(
        self,
        *,
        name: str | None = None,
        unit_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[UnitDefinition]:
        """Return an exact unit revision."""
        value = await self.get_definition(name=name, definition_id=unit_id, revision=revision)
        return _view(value=value, body_type=UnitDefinition, view_type=Definition[UnitDefinition])

    async def list_definitions(
        self,
        *,
        status: DefinitionStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Definition]:
        """Page through current definitions within this model."""
        if status is not None:
            require_exact(value=status, expected=DefinitionStatus, field="Definition status")
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.definitions.list(
                scope=self.scope,
                status=status,
                limit=limit,
                cursor=cursor,
            )

    async def get_definition_history(
        self,
        *,
        definition_id: DefinitionId,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Definition]:
        """Inspect immutable revisions for one model-local identity."""
        require_exact(value=definition_id, expected=DefinitionId, field="Definition ID")
        async with self._open_review() as transaction, transaction.begin():
            return await transaction.definitions.history(
                scope=self.scope,
                definition_id=definition_id,
                limit=limit,
                cursor=cursor,
            )


def _view[T: DefinitionBody](
    *,
    value: Definition,
    body_type: type[T],
    view_type: type[Definition[T]],
) -> Definition[T]:
    if not isinstance(value.body, body_type):
        raise DefinitionKindMismatchError
    return view_type(
        id=value.id,
        scope=value.scope,
        revision=value.revision,
        name=value.name,
        display_name=value.display_name,
        meaning=value.meaning,
        body=value.body,
        aliases=value.aliases,
        terminology=value.terminology,
        origin=value.origin,
        status=value.status,
        basis=value.basis,
        decision_ids=value.decision_ids,
        rationale=value.rationale,
        baseline_definition_id=value.baseline_definition_id,
        replacement_ids=value.replacement_ids,
    )
