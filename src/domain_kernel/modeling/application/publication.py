"""Prepare, authorize and compare immutable model releases."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel.bundles import DomainModelBundle, require_valid_bundle
from domain_kernel.modeling.domain.comparison import compare_candidates
from domain_kernel.modeling.domain.publications import (
    Approval,
    Publication,
    require_current_publication,
)
from domain_kernel.modeling.domain.snapshots import Candidate
from domain_kernel.modeling.domain.validation import VALIDATOR_FINGERPRINT, ModelReadinessEvaluator
from domain_kernel.publication.domain.errors.publication_blocked_error import (
    PublicationBlockedError,
)
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.shared.application.persistence import Invocation, OperationOutcome
from domain_kernel.shared.contracts import CandidatePin, ModelVersion
from domain_kernel.shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel.shared.domain.record_encoding import record_bytes, record_value
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact, require_text

if TYPE_CHECKING:
    from domain_kernel.modeling.application.compilation_ports import (
        CompilationRepository,
        CompiledSnapshot,
    )
    from domain_kernel.modeling.application.compiler import ModelCompiler
    from domain_kernel.modeling.application.publication_ports import PublicationRepository
    from domain_kernel.modeling.application.validation import CompositeModelValidator
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.modeling.domain.snapshots import PublicationRules
    from domain_kernel.shared.application.persistence import (
        AuditRepository,
        IdempotencyRepository,
        Lease,
        TransactionManager,
    )
    from domain_kernel.shared.contracts import ModelScope, SnapshotReference
    from domain_kernel.shared.domain.changes import ChangeSet


def _pin(*, candidate: Candidate) -> CandidatePin:
    return CandidatePin(
        scope=candidate.scope,
        candidate_id=candidate.id,
        content_hash=candidate.content_hash,
    )


def _ready_or_blocked(*, publication: Publication) -> Publication:
    if not publication.ready:
        raise PublicationBlockedError(publication=publication)
    return publication


@final
class PublicationService:
    """Coordinate exact captured state and separate host authorization."""

    def __init__(  # noqa: PLR0913 - Inject the narrow bound capabilities.
        self,
        *,
        compiler: ModelCompiler,
        compilation: CompilationRepository,
        publications: PublicationRepository,
        operations: IdempotencyRepository,
        audit: AuditRepository,
        transaction: TransactionManager,
        rules: PublicationRules,
        validator: CompositeModelValidator,
    ) -> None:
        """Bind operation capabilities and immutable publication rules."""
        self._compiler = compiler
        self._compilation = compilation
        self._publications = publications
        self._operations = operations
        self._audit = audit
        self._transaction = transaction
        self._rules = rules
        self._validator = validator
        self._policy = hash_json(value=record_value(value=(rules, validator.fingerprint))).value

    async def prepare(
        self,
        *,
        model: ModelInfo,
        actor: str,
        idempotency_key: str | None,
    ) -> Publication:
        """Capture and compute once, then persist a ready or blocked outcome."""
        request = Invocation.resolve(
            project_id=model.scope.project_id,
            model_id=model.scope.model_id,
            operation="prepare_publication",
            actor=actor,
            key=idempotency_key,
            intent=model.scope.model_id.value
            if self._validator.fingerprint == VALIDATOR_FINGERPRINT
            else (model.scope.model_id.value, self._validator.fingerprint),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=request, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "publication":
                    raise StaleStateError(message="Reload the prepared publication")
                publication = await self._publications.preparation(
                    scope=model.scope,
                    publication_id=PublicationId(value=claim.resource_id),
                )
                return _ready_or_blocked(publication=publication)
            snapshot = await self._compiler.capture(model=model)
            previous = await self._comparison_base(candidate=snapshot.candidate)
        try:
            publication = await self._evaluate(snapshot=snapshot, previous=previous)
            await self._save_preparation(
                model=model,
                snapshot=snapshot,
                publication=publication,
                request=request,
                lease=claim,
                prior=previous,
            )
        except BaseException:
            # A completed outcome may already be committed even if acknowledgment was lost.
            with suppress(StaleStateError):
                async with self._transaction.begin():
                    await self._operations.release(invocation=request, lease=claim)
            raise
        return _ready_or_blocked(publication=publication)

    async def _comparison_base(self, *, candidate: Candidate) -> DomainModelBundle | None:
        previous = await self._publications.latest(scope=candidate.scope)
        if previous is not None or candidate.baseline is None:
            return previous
        return await self._registered(value=candidate.baseline)

    async def _evaluate(
        self,
        *,
        snapshot: CompiledSnapshot,
        previous: DomainModelBundle | None,
    ) -> Publication:
        candidate = snapshot.candidate
        report = await self._validator.validate(
            candidate=candidate, reference_pack=snapshot.reference_pack
        )
        readiness = ModelReadinessEvaluator(
            validator_fingerprint=self._validator.fingerprint
        ).evaluate(
            candidate=candidate,
            validation=report,
            reference_pack=snapshot.reference_pack,
            review=snapshot.review,
            rules=self._rules,
        )
        changes = compare_candidates(
            before=None if previous is None else previous.publication.candidate,
            after=candidate,
            before_pin=None if previous is None else previous.model_version,
            after_pin=_pin(candidate=candidate),
        )
        return Publication(
            id=PublicationId(value=uuid4().hex),
            scope=candidate.scope,
            candidate=candidate,
            reference_pack=snapshot.reference_pack,
            validation=report,
            readiness=readiness,
            changes=changes,
            policy_fingerprint=self._policy,
            prepared_at=datetime.now(tz=UTC),
        )

    async def _save_preparation(  # noqa: PLR0913 - Persist the exact capture using its lease.
        self,
        *,
        model: ModelInfo,
        snapshot: CompiledSnapshot,
        publication: Publication,
        request: Invocation,
        lease: Lease,
        prior: DomainModelBundle | None,
    ) -> None:
        async with self._transaction.begin():
            renewed = await self._operations.renew(invocation=request, lease=lease)
            current = await self._compiler.capture(model=model)
            require_current_publication(
                publication=publication,
                current=current.candidate,
                policy_fingerprint=self._policy,
            )
            if await self._comparison_base(candidate=current.candidate) != prior:
                raise StaleStateError(
                    message="Inspect a fresh comparison with the current publication baseline"
                )
            await self._compilation.add_candidate(snapshot=snapshot)
            await self._compilation.add_report(report=publication.validation)
            await self._publications.add_preparation(publication=publication)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=model.scope.project_id,
                    model_id=model.scope.model_id,
                    action=AuditAction.PREPARE_PUBLICATION,
                    outcome=AuditOutcome.SUCCEEDED if publication.ready else AuditOutcome.BLOCKED,
                    actor=request.actor,
                    recorded_at=publication.prepared_at,
                    before=(),
                    after=(
                        AuditResource(
                            resource_id=publication.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=publication)),
                        ),
                    ),
                )
            )
            await self._operations.complete(
                invocation=request,
                lease=renewed,
                outcome=OperationOutcome(
                    resource_kind="publication",
                    resource_id=publication.id.value,
                ),
            )

    async def publish(  # noqa: PLR0913 - Exact version, actor and reason bind the outcome.
        self,
        *,
        model: ModelInfo,
        publication: Publication,
        version: str,
        actor: str,
        reason: str,
        idempotency_key: str | None,
    ) -> DomainModelBundle:
        """Authorize the inspected preparation and commit the version once."""
        require_exact(value=publication, expected=Publication, field="Publication")
        require_text(value=version, field="Release version")
        require_text(value=reason, field="Release reason")
        if publication.scope != model.scope:
            raise ScopeMismatchError
        invocation = Invocation.resolve(
            project_id=model.scope.project_id,
            model_id=model.scope.model_id,
            operation="publish",
            actor=actor,
            key=idempotency_key,
            intent=record_value(value=(publication, version, reason)),
        )
        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, OperationOutcome):
                if claim.resource_kind != "bundle" or claim.resource_version != version:
                    raise StaleStateError(message="Reload the original published version")
                bundle = await self._publications.bundle(scope=model.scope, version=version)
                if bundle.id.value != claim.resource_id:
                    raise StaleStateError(message="Reload the exact published bundle")
                return bundle
            stored = await self._publications.preparation(
                scope=model.scope,
                publication_id=publication.id,
            )
            if stored != publication:
                raise StaleStateError(message="Reload the exact inspected preparation")
            _ = _ready_or_blocked(publication=stored)
            current = await self._compiler.capture(model=model)
            require_current_publication(
                publication=stored,
                current=current.candidate,
                policy_fingerprint=self._policy,
            )
            bundle = self._authorize(
                publication=stored, version=version, actor=actor, reason=reason
            )
            await self._publications.add_bundle(bundle=bundle)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=model.scope.project_id,
                    model_id=model.scope.model_id,
                    action=AuditAction.PUBLISH,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    reason=reason,
                    recorded_at=bundle.published_at,
                    before=(
                        AuditResource(
                            resource_id=stored.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=stored)),
                        ),
                    ),
                    after=(
                        AuditResource(
                            resource_id=bundle.id, revision=None, content_hash=bundle.content_hash
                        ),
                        AuditResource(
                            resource_id=bundle.approval.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=bundle.approval)),
                        ),
                    ),
                )
            )
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="bundle",
                    resource_id=bundle.id.value,
                    resource_version=version,
                ),
            )
            return bundle

    def _authorize(
        self,
        *,
        publication: Publication,
        version: str,
        actor: str,
        reason: str,
    ) -> DomainModelBundle:
        now = datetime.now(tz=UTC)
        candidate = publication.candidate
        approval = Approval(
            id=ApprovalId(value=uuid4().hex),
            scope=publication.scope,
            publication_id=publication.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.content_hash,
            validation_id=publication.validation.id,
            workspace_revision=candidate.workspace_revision,
            review_snapshot_version=candidate.review_snapshot_version,
            policy_fingerprint=publication.policy_fingerprint,
            actor=actor,
            reason=reason,
            approved_at=now,
        )
        bundle = DomainModelBundle.from_approved(
            publication=publication,
            approval=approval,
            bundle_id=BundleId(value=uuid4().hex),
            version=version,
            now=now,
        )
        require_valid_bundle(bundle=bundle)
        return bundle

    async def diff(
        self,
        *,
        model: ModelInfo,
        before: DomainModelBundle | Candidate | ModelVersion,
        after: DomainModelBundle | Candidate | ModelVersion,
    ) -> ChangeSet:
        """Resolve both exact stored inputs before performing an immutable comparison."""
        async with self._transaction.begin():
            later, after_pin = await self._resolve(scope=model.scope, value=after)
            if type(before) not in (DomainModelBundle, ModelVersion, Candidate):
                raise TypeError("Compare an exact bundle, model version or candidate")
            if before.scope == model.scope:
                earlier, before_pin = await self._resolve(scope=model.scope, value=before)
            else:
                expected = later.baseline
                if isinstance(before, Candidate) or expected is None:
                    raise ScopeMismatchError
                declared = before.model_version if isinstance(before, DomainModelBundle) else before
                if declared != expected:
                    raise ScopeMismatchError
                bundle = await self._registered(value=before)
                earlier, before_pin = bundle.publication.candidate, bundle.model_version
        return compare_candidates(
            before=earlier,
            before_pin=before_pin,
            after=later,
            after_pin=after_pin,
        )

    async def _registered(self, *, value: DomainModelBundle | ModelVersion) -> DomainModelBundle:
        if isinstance(value, DomainModelBundle):
            require_valid_bundle(bundle=value)
        bundle = await self._publications.bundle(scope=value.scope, version=value.version)
        if (bundle if isinstance(value, DomainModelBundle) else bundle.model_version) != value:
            raise StaleStateError(message="Reload the registered model version before comparison")
        return bundle

    async def _resolve(
        self,
        *,
        scope: ModelScope,
        value: DomainModelBundle | Candidate | ModelVersion,
    ) -> tuple[Candidate, SnapshotReference]:
        if type(value) not in (DomainModelBundle, ModelVersion, Candidate):
            raise TypeError("Compare an exact bundle, model version or candidate")
        if value.scope != scope:
            raise ScopeMismatchError
        if isinstance(value, Candidate):
            stored = (
                await self._compilation.get_candidate(scope=scope, candidate_id=value.id)
            ).candidate
            if stored != value:
                raise StaleStateError(message="Reload the exact candidate before comparison")
            return stored, _pin(candidate=stored)
        bundle = await self._registered(value=value)
        return bundle.publication.candidate, bundle.model_version
