"""Evaluate and store validation for the exact candidate supplied by the caller."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.business_decisions import RuleDefinition
from domain_kernel._shared.domain.data_shapes import ConstraintLanguage
from domain_kernel._shared.domain.record_encoding import record_bytes
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.application.validation_ports import ConstraintSupport
from domain_kernel.modeling.domain.snapshots import Candidate, ValidationReport
from domain_kernel.modeling.domain.validation import (
    VALIDATOR_FINGERPRINT,
    ModelAcceptanceEvaluator,
    ModelInvariantValidator,
    validator_fingerprint,
)
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import DomainKernelError, StaleStateError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact, require_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.persistence import AuditRepository, TransactionManager
    from domain_kernel.modeling.application.compilation_ports import CompilationRepository
    from domain_kernel.modeling.application.validation_ports import SemanticValidator
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.contracts import ModelScope


def validate_candidate(
    *,
    candidate: Candidate,
    reference_pack: ReferencePack | None = None,
) -> ValidationReport:
    """Evaluate the bounded core invariants and predicates on one immutable candidate."""
    return ValidationReport(
        id=ValidationReportId(value=uuid4().hex),
        scope=candidate.scope,
        candidate_id=candidate.id,
        candidate_hash=candidate.content_hash,
        validator_fingerprint=VALIDATOR_FINGERPRINT,
        reference_pack=candidate.reference_pack,
        issues=ModelInvariantValidator().validate(
            candidate=candidate, reference_pack=reference_pack
        ),
        acceptance=ModelAcceptanceEvaluator().evaluate(candidate=candidate),
    )


@final
class CompositeModelValidator:
    """Run core invariants and every explicitly selected required semantic validator."""

    def __init__(self, *, semantic: Sequence[SemanticValidator] = ()) -> None:
        """Capture validation capabilities without evaluating any candidate."""
        self._semantic = tuple(semantic)
        self._fingerprints = tuple(item.fingerprint for item in self._semantic)
        self.fingerprint = validator_fingerprint(semantic=self._fingerprints)
        self._languages = frozenset(
            language
            for item in self._semantic
            if isinstance(item, ConstraintSupport)
            for language in item.constraint_languages
        )

    async def validate(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
    ) -> ValidationReport:
        """Accumulate independent results without letting an adapter replace core checks."""
        core = validate_candidate(candidate=candidate, reference_pack=reference_pack)
        issues = [
            Issue(
                code="constraint_validator_missing",
                path=("definitions", definition.id.value, "constraints", offset),
                message="Configure a required validator supporting this authored constraint.",
            )
            for definition in candidate.content.definitions
            if isinstance(definition.body, RuleDefinition)
            for offset, constraint in enumerate(definition.body.constraints)
            if constraint.language is not ConstraintLanguage.TEXT
            and constraint.language not in self._languages
        ]
        for validator in self._semantic:
            try:
                report = await validator.validate(
                    candidate=candidate, reference_pack=reference_pack
                )
            except DomainKernelError:
                issues.append(
                    Issue(
                        code="semantic_validator_failed",
                        path=("validation",),
                        message="Inspect the configured required semantic validator.",
                    )
                )
                continue
            if (
                type(report) is not ValidationReport
                or report.scope != core.scope
                or report.candidate_id != core.candidate_id
                or report.candidate_hash != core.candidate_hash
                or report.reference_pack != core.reference_pack
                or report.validator_fingerprint != validator.fingerprint
            ):
                issues.append(
                    Issue(
                        code="semantic_validator_mismatch",
                        path=("validation",),
                        message="Return validation for the exact captured candidate and adapter.",
                    )
                )
                continue
            issues.extend(report.issues)
        return replace(
            core,
            validator_fingerprint=self.fingerprint,
            issues=(*core.issues, *issues),
            semantic_fingerprints=self._fingerprints,
        )


@final
class CandidateValidation:
    """Record the result of validation without changing its input candidate."""

    def __init__(
        self,
        *,
        scope: ModelScope,
        compilation: CompilationRepository,
        audit: AuditRepository,
        transaction: TransactionManager,
        validator: CompositeModelValidator,
    ) -> None:
        """Bind the collaborators for this operation."""
        self._scope = scope
        self._compilation = compilation
        self._audit = audit
        self._transaction = transaction
        self._validator = validator

    async def validate(self, *, candidate: Candidate, actor: str) -> ValidationReport:
        """Reload the stored snapshot, compute outside a transaction, and record the result."""
        require_text(value=actor, field="Actor")
        require_exact(value=candidate, expected=Candidate, field="Candidate")
        if candidate.scope != self._scope:
            raise StaleStateError(message="Use a candidate from this exact model")
        async with self._transaction.begin():
            snapshot = await self._compilation.get_candidate(
                scope=self._scope,
                candidate_id=candidate.id,
            )
            if snapshot.candidate != candidate:
                raise StaleStateError(message="Reload the exact persisted candidate")
        report = await self._validator.validate(
            candidate=snapshot.candidate,
            reference_pack=snapshot.reference_pack,
        )
        async with self._transaction.begin():
            await self._compilation.add_report(report=report)
            await self._audit.append(
                record=AuditRecord(
                    id=AuditId(value=uuid4().hex),
                    project_id=self._scope.project_id,
                    model_id=self._scope.model_id,
                    action=AuditAction.VALIDATE,
                    outcome=AuditOutcome.SUCCEEDED,
                    actor=actor,
                    recorded_at=datetime.now(tz=UTC),
                    before=(
                        AuditResource(
                            resource_id=candidate.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=candidate)),
                        ),
                    ),
                    after=(
                        AuditResource(
                            resource_id=report.id,
                            revision=None,
                            content_hash=hash_bytes(content=record_bytes(value=report)),
                        ),
                    ),
                )
            )
        return report
