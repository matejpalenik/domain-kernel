"""Public handle for an independently managed model workspace."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Never, final

from domain_kernel._shared.domain.artifacts import SemanticGraphRole
from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    RestoreDefinition,
    RetireDefinition,
    ReviseDefinition,
)
from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    DefinitionBody,
    Process,
    RelationshipDefinition,
    UnitDefinition,
    typed_definition,
)
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.authoring import UNSET, Unset
from domain_kernel.bundles import DomainModelBundle, require_valid_bundle
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.application.compilation_ports import CompilationTransaction
from domain_kernel.modeling.application.compiler import ModelCompiler
from domain_kernel.modeling.application.dependencies import DependencyTransaction
from domain_kernel.modeling.application.exports import PublicationExport, bundle_payload
from domain_kernel.modeling.application.json_schema_projection import JsonSchemaExporter
from domain_kernel.modeling.application.publication import PublicationService
from domain_kernel.modeling.application.publication_ports import PublicationTransaction
from domain_kernel.modeling.application.rdf_projection import rdf_payload
from domain_kernel.modeling.application.validation import (
    CandidateValidation,
    CompositeModelValidator,
)
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.definition_errors import DefinitionKindMismatchError
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.interchange import (
    JsonSchemaProjectionRequest,
    RdfProjectionRequest,
    require_projection_request,
)
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.review.application.coordinated_review import CoordinatedReview
from domain_kernel.review.application.manual_review import ManualReview
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import Page
from domain_kernel.shared.errors import MissingCapabilityError, ScopeMismatchError, StaleStateError
from domain_kernel.shared.validation import is_non_string_sequence, require_exact, require_text

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.persistence import UnitOfWorkFactory
    from domain_kernel._shared.domain.audit import Artifact, AuditRecord
    from domain_kernel._shared.domain.authoring import ModelChangePlan
    from domain_kernel._shared.domain.changes import ChangeSet
    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.modeling.application.exports import ExportDestination
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.modeling.domain.publications import Publication
    from domain_kernel.modeling.domain.snapshots import (
        Candidate,
        PublicationRules,
        ValidationReport,
    )
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.reference_packs.domain.contracts import DefinitionBinding, Pattern
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.models import (
        CaseDecision,
        DecisionRecord,
        ReviewCase,
        ReviewImpact,
        ReviewReceipt,
    )
    from domain_kernel.shared.contracts import ModelScope, ModelVersion
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


@final
class Model:
    """Read the model's captured metadata and attributed history."""

    def __init__(
        self,
        *,
        info: ModelInfo,
        resources: UnitOfWorkFactory[CatalogTransaction],
        publication_rules: PublicationRules,
        artifact_destinations: Mapping[str, ExportDestination] | None = None,
        validator: CompositeModelValidator | None = None,
    ) -> None:
        """Bind a detached metadata snapshot to the client's resource factory."""
        self._info = info
        self._resources = resources
        self._publication_rules = publication_rules
        self._artifact_destinations = artifact_destinations
        self._validator = CompositeModelValidator() if validator is None else validator

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
    async def _open_compilation(self) -> AsyncGenerator[CompilationTransaction]:
        async with self._resources() as transaction:
            if not isinstance(transaction, CompilationTransaction):
                raise MissingCapabilityError(
                    message="Configure persistence for compiled model snapshots"
                )
            yield transaction

    @staticmethod
    def _compiler(*, transaction: CompilationTransaction) -> ModelCompiler:
        return ModelCompiler(
            models=transaction.models,
            definitions=transaction.definitions,
            reviews=transaction.reviews,
            compilation=transaction.compilation,
            audit=transaction.audit,
            operations=transaction.operations,
            transaction=transaction,
            packs=transaction.packs if isinstance(transaction, PackSelectionTransaction) else None,
            resolver=transaction.dependencies
            if isinstance(transaction, DependencyTransaction)
            else None,
        )

    async def compile(self, *, actor: str) -> Candidate:
        """Capture and save the current reviewed workspace."""
        async with self._open_compilation() as transaction:
            return await self._compiler(transaction=transaction).compile(
                model=self._info, actor=actor
            )

    async def get_candidate(self, *, candidate_id: CandidateId) -> Candidate:
        """Read one exact compiled model snapshot."""
        require_exact(value=candidate_id, expected=CandidateId, field="Candidate ID")
        async with self._open_compilation() as transaction, transaction.begin():
            stored = await transaction.compilation.get_candidate(
                scope=self.scope,
                candidate_id=candidate_id,
            )
            return stored.candidate

    async def validate(self, *, actor: str, candidate: Candidate) -> ValidationReport:
        """Evaluate and store findings from the exact captured candidate."""
        async with self._open_compilation() as transaction:
            return await CandidateValidation(
                scope=self.scope,
                compilation=transaction.compilation,
                audit=transaction.audit,
                transaction=transaction,
                validator=self._validator,
            ).validate(candidate=candidate, actor=actor)

    @asynccontextmanager
    async def _open_publications(self) -> AsyncGenerator[PublicationTransaction]:
        async with self._resources() as transaction:
            if not isinstance(transaction, PublicationTransaction):
                raise MissingCapabilityError(message="Configure persistence for model publications")
            yield transaction

    def _publication_service(self, *, transaction: PublicationTransaction) -> PublicationService:
        return PublicationService(
            compiler=self._compiler(transaction=transaction),
            compilation=transaction.compilation,
            publications=transaction.publications,
            operations=transaction.operations,
            audit=transaction.audit,
            transaction=transaction,
            validator=self._validator,
            rules=self._publication_rules,
        )

    async def prepare_publication(
        self,
        *,
        actor: str,
        idempotency_key: str | None = None,
    ) -> Publication:
        """Save the inspected candidate and readiness, raising with any saved blockers."""
        async with self._open_publications() as transaction:
            return await self._publication_service(transaction=transaction).prepare(
                model=self.info,
                actor=actor,
                idempotency_key=idempotency_key,
            )

    async def get_publication(self, *, publication_id: PublicationId) -> Publication:
        """Read an exact saved preparation, including a blocked result."""
        require_exact(value=publication_id, expected=PublicationId, field="Publication ID")
        async with self._open_publications() as transaction, transaction.begin():
            return await transaction.publications.preparation(
                scope=self.scope,
                publication_id=publication_id,
            )

    async def list_publications(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Publication]:
        """Page inspected and blocked preparations in the order recorded."""
        async with self._open_publications() as transaction, transaction.begin():
            return await transaction.publications.list_preparations(
                scope=self.scope,
                limit=limit,
                cursor=cursor,
            )

    async def publish(
        self,
        *,
        publication: Publication,
        version: str,
        actor: str,
        reason: str,
        idempotency_key: str | None = None,
    ) -> DomainModelBundle:
        """Authorize and store the exact inspected publication as a named version."""
        async with self._open_publications() as transaction:
            return await self._publication_service(transaction=transaction).publish(
                model=self.info,
                publication=publication,
                version=version,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key,
            )

    async def get_version(self, *, version: str) -> DomainModelBundle:
        """Open one immutable released version by its exact label."""
        require_text(value=version, field="Release version")
        async with self._open_publications() as transaction, transaction.begin():
            return await transaction.publications.bundle(scope=self.scope, version=version)

    async def export(  # noqa: PLR0913 - Exact source, configured destination and retry key.
        self,
        *,
        actor: str,
        bundle: DomainModelBundle,
        store: str,
        path: str,
        request: JsonSchemaProjectionRequest | RdfProjectionRequest | None = None,
        role: SemanticGraphRole | Unset = UNSET,
        idempotency_key: str | None = None,
    ) -> Artifact:
        """Write the exact registered release or one assessed projection."""
        require_exact(value=bundle, expected=DomainModelBundle, field="Published model bundle")
        require_text(value=actor, field="Actor")
        require_text(value=store, field="Artifact store")
        if request is not None:
            require_projection_request(request=request)
        if role is not UNSET and not isinstance(request, RdfProjectionRequest):
            raise TypeError("Select a graph role only for an RDF projection")
        if bundle.scope != self.scope:
            raise ScopeMismatchError
        require_valid_bundle(bundle=bundle)
        async with self._open_publications() as transaction:
            async with transaction.begin():
                registered = await transaction.publications.bundle(
                    scope=self.scope, version=bundle.version
                )
                if registered != bundle:
                    raise StaleStateError(message="Reload the exact registered publication")
            destination = (
                None
                if self._artifact_destinations is None
                else self._artifact_destinations.get(store)
            )
            if destination is None:
                raise MissingCapabilityError(message="Configure the named artifact destination")
            if isinstance(request, RdfProjectionRequest):
                resolved_role = SemanticGraphRole.ONTOLOGY if role is UNSET else role
                require_exact(
                    value=resolved_role, expected=SemanticGraphRole, field="Semantic role"
                )
                if isinstance(resolved_role, Unset):
                    raise TypeError("Select a semantic graph role")
                rendered = await asyncio.to_thread(
                    rdf_payload,
                    bundle=registered,
                    request=request,
                    role=resolved_role,
                )
            elif isinstance(request, JsonSchemaProjectionRequest):
                rendered = await asyncio.to_thread(
                    JsonSchemaExporter().export,
                    bundle=registered,
                    request=request,
                )
            else:
                rendered = bundle_payload(bundle=registered, request=request)
            return await PublicationExport(
                actor=actor,
                bundle=registered,
                store=store,
                path=path,
                idempotency_key=idempotency_key,
            ).deliver(
                transaction=transaction,
                destination=destination,
                payload=rendered,
            )

    async def list_versions(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[DomainModelBundle]:
        """Page immutable released versions in publication order."""
        async with self._open_publications() as transaction, transaction.begin():
            return await transaction.publications.list_versions(
                scope=self.scope,
                limit=limit,
                cursor=cursor,
            )

    async def diff(
        self,
        *,
        before: DomainModelBundle | ModelVersion | Candidate,
        after: DomainModelBundle | ModelVersion | Candidate,
    ) -> ChangeSet:
        """Compare exact workspace snapshots or the direct published baseline."""
        async with self._open_publications() as transaction:
            return await self._publication_service(transaction=transaction).diff(
                model=self.info,
                before=before,
                after=after,
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
            packs=transaction.packs if isinstance(transaction, PackSelectionTransaction) else None,
            resolver=transaction.dependencies
            if isinstance(transaction, DependencyTransaction)
            else None,
        )

    def _coordinated_service(self, *, transaction: ReviewTransaction) -> CoordinatedReview:
        return CoordinatedReview(
            scope=self.scope,
            definitions=transaction.definitions,
            reviews=transaction.reviews,
            audit=transaction.audit,
            operations=transaction.operations,
            revisions=transaction.revisions,
            transaction=transaction,
            packs=transaction.packs if isinstance(transaction, PackSelectionTransaction) else None,
            resolver=transaction.dependencies
            if isinstance(transaction, DependencyTransaction)
            else None,
        )

    async def propose_change_plan(
        self,
        *,
        actor: str,
        plan: ModelChangePlan,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Reserve one authored plan and its immutable member snapshots."""
        async with self._open_review() as transaction:
            return await self._coordinated_service(transaction=transaction).submit_plan(
                actor=actor,
                plan=plan,
                idempotency_key=idempotency_key,
            )

    async def propose_pattern(
        self,
        *,
        actor: str,
        pattern: Pattern,
        bindings: Sequence[DefinitionBinding] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Reserve a local graph from an exact selected pack for explicit review."""
        async with self._open_review() as transaction:
            if not isinstance(transaction, PackSelectionTransaction):
                raise MissingCapabilityError(message="Configure durable selected-pack persistence")
            return await self._coordinated_service(transaction=transaction).adopt_pattern(
                actor=actor,
                pattern=pattern,
                bindings=bindings,
                reason=reason,
                idempotency_key=idempotency_key,
                packs=transaction.packs,
            )

    async def propose_reference_alignment(
        self,
        *,
        actor: str,
        local_definition: Definition,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Open explicit review of the current local definition and selected reference pack."""
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).propose_reference_alignment(
                actor=actor,
                local_definition=local_definition,
                reason=reason,
                idempotency_key=idempotency_key,
            )

    async def propose_change_set(
        self,
        *,
        actor: str,
        decisions: Sequence[CaseDecision],
        expected_workspace_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Group explicit decisions on existing inspected leaf cases."""
        async with self._open_review() as transaction:
            return await self._coordinated_service(transaction=transaction).group_cases(
                actor=actor,
                decisions=decisions,
                expected_workspace_revision=expected_workspace_revision,
                reason=reason,
                idempotency_key=idempotency_key,
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

    async def propose_definition_revision(  # noqa: PLR0913 - Replace the declared authored fields.
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        display_name: str,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Never] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Propose a full next revision of the exact inspected definition."""
        if not is_non_string_sequence(evidence) or evidence:
            raise ValueError("Source evidence requires a captured source revision")
        terms = Terminology() if terminology is None else terminology

        def revised(before: Definition) -> ReviseDefinition:
            return ReviseDefinition(
                before=before,
                reason=reason,
                content=AuthoredContent(
                    name=before.name,
                    display_name=display_name,
                    meaning=meaning,
                    body=body,
                    aliases=aliases,
                    terminology=terms,
                    schema_origins=before.schema_origins,
                ),
            )

        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).propose_lifecycle(
                actor=actor,
                definition_id=definition_id,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                operation=revised,
                intent=record_value(
                    value=(
                        "revise",
                        display_name,
                        meaning,
                        body,
                        aliases,
                        terms,
                        reason,
                    )
                ),
            )

    async def propose_definition_retirement(  # noqa: PLR0913 - Capture replacement lineage.
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        replacement_ids: Sequence[DefinitionId] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Propose retaining the current definition as a tombstone."""
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).propose_lifecycle(
                actor=actor,
                definition_id=definition_id,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                operation=lambda before: RetireDefinition(
                    before=before,
                    reason=reason,
                    replacement_ids=replacement_ids,
                ),
                intent=record_value(value=("retire", replacement_ids, reason)),
            )

    async def propose_definition_restoration(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase:
        """Propose restoring the same identity and stable name."""
        async with self._open_review() as transaction:
            return await self._review_service(transaction=transaction).propose_lifecycle(
                actor=actor,
                definition_id=definition_id,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                operation=lambda before: RestoreDefinition(before=before, reason=reason),
                intent=record_value(value=("restore", reason)),
            )

    async def preview_changes(self, *, case: ReviewCase, decision: ReviewAction) -> ReviewImpact:
        """Inspect prospective effects from the exact supplied case."""
        async with self._open_review() as transaction:
            if case.kind is CaseKind.CHANGE_SET:
                return await self._coordinated_service(transaction=transaction).preview(
                    case=case,
                    decision=decision,
                )
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
            if case.kind is CaseKind.CHANGE_SET:
                return await self._coordinated_service(transaction=transaction).decide(
                    case=case,
                    decision=decision,
                    actor=actor,
                    idempotency_key=idempotency_key,
                )
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
            stored = await transaction.definitions.get(
                scope=self.scope,
                name=name,
                definition_id=definition_id,
                revision=revision,
            )
        if isinstance(stored.body, ProcessDefinition):
            return typed_definition(value=stored, body_type=ProcessDefinition, view_type=Process)
        return stored

    async def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Concept:
        """Return an inspected concept with its local attribute and key reads."""
        value = await self.get_definition(name=name, definition_id=concept_id, revision=revision)
        concept = typed_definition(value=value, body_type=ConceptDefinition, view_type=Concept)
        if not isinstance(concept, Concept):
            raise DefinitionKindMismatchError
        return concept

    async def get_process(
        self,
        *,
        name: str | None = None,
        process_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Process:
        """Read an exact process revision with local part inspection."""
        value = await self.get_definition(name=name, definition_id=process_id, revision=revision)
        if not isinstance(value, Process):
            raise DefinitionKindMismatchError
        return value

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
        return typed_definition(
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
        return typed_definition(
            value=value, body_type=UnitDefinition, view_type=Definition[UnitDefinition]
        )

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
