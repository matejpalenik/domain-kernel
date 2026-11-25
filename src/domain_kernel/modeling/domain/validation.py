"""Pure acceptance, structural validation and readiness policies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.dependencies import dependency_closure, dependency_definitions
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.snapshots import Readiness, ReadinessCheck
from domain_kernel.reference_packs.domain.dispositions import (
    coverage_blockers,
    reference_context_issues,
)
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.enums.check_outcome import CheckOutcome
from domain_kernel.shared.domain.enums.check_requirement import CheckRequirement
from domain_kernel.shared.domain.enums.evidence_basis import EvidenceBasis
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.policies.shape_graph import (
    shape_references,
    validate_body_graph,
    validate_model_shapes,
)
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.acceptance_check_result import AcceptanceCheckResult
from domain_kernel.shared.domain.value_objects.distinct_definitions_check import (
    DistinctDefinitionsCheck,
)
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import InvalidBundleError
from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.modeling.domain.snapshots import (
        Candidate,
        PublicationRules,
        ReviewSnapshot,
        ValidationReport,
    )
    from domain_kernel.reference_packs.domain.packs import ReferencePack
    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.types.acceptance_predicate import AcceptancePredicate
    from domain_kernel.shared.domain.types.definition_body import DefinitionBody
    from domain_kernel.shared.domain.value_objects.quantity_required_check import (
        QuantityRequiredCheck,
    )
    from domain_kernel.shared.identifiers.content_hash import ContentHash

VALIDATOR_FINGERPRINT = "core-1"
_EVALUATOR_HASH = hash_json(value={"model_acceptance": 1})


def validator_fingerprint(*, semantic: Sequence[str]) -> str:
    """Identify the core and ordered semantic validators captured in a report."""
    return (
        hash_json(value=(VALIDATOR_FINGERPRINT, semantic)).value
        if semantic
        else VALIDATOR_FINGERPRINT
    )


def _quantity_closure(
    *,
    structure: DefinitionId,
    definitions: Mapping[DefinitionId, Definition],
) -> tuple[Issue, ...]:
    bodies: dict[DefinitionReference, DefinitionBody] = {}
    outstanding: list[DefinitionReference] = [structure]
    while outstanding:
        item = outstanding.pop()
        if not isinstance(item, DefinitionId) or item in bodies:
            continue
        definition = definitions.get(item)
        if definition is None:
            continue
        bodies[item] = definition.body
        outstanding.extend(edge.target for edge in shape_references(body=definition.body))
    return validate_body_graph(bodies=bodies)


def _distinct(
    *, predicate: DistinctDefinitionsCheck, definitions: Mapping[DefinitionId, Definition]
) -> tuple[CheckOutcome, str]:
    if not isinstance(predicate.left, DefinitionId) or not isinstance(
        predicate.right, DefinitionId
    ):
        return CheckOutcome.UNSUPPORTED, "Materialize the exact non-local check targets"
    if predicate.left not in definitions or predicate.right not in definitions:
        return CheckOutcome.UNKNOWN, "Resolve both checked identities in the candidate"
    if predicate.left == predicate.right:
        return CheckOutcome.FAIL, "The check resolves both sides to the same identity"
    return CheckOutcome.PASS, ""


def _quantity(
    *, predicate: QuantityRequiredCheck, definitions: Mapping[DefinitionId, Definition]
) -> tuple[CheckOutcome, str]:
    if not isinstance(predicate.structure, DefinitionId):
        return CheckOutcome.UNSUPPORTED, "Materialize the exact non-local structured value"
    target = definitions.get(predicate.structure)
    if target is None:
        return CheckOutcome.UNKNOWN, "Resolve the checked quantity in the candidate"
    if not isinstance(target.body, StructuredValueDefinition) or target.body.quantity is None:
        return CheckOutcome.FAIL, "Use a structured value with a validated quantity binding"
    if _quantity_closure(structure=predicate.structure, definitions=definitions):
        return CheckOutcome.FAIL, "Resolve the quantity's closed unit vocabulary and active units"
    return CheckOutcome.PASS, ""


def _evaluate_predicate(
    *,
    predicate: AcceptancePredicate,
    definitions: Mapping[DefinitionId, Definition],
) -> tuple[CheckOutcome, str]:
    if isinstance(predicate, ManualCriterion):
        return CheckOutcome.UNKNOWN, "This criterion requires recorded human judgment"
    if isinstance(predicate, DistinctDefinitionsCheck):
        return _distinct(predicate=predicate, definitions=definitions)
    return _quantity(predicate=predicate, definitions=definitions)


class ModelAcceptanceEvaluator:
    """Evaluate bounded predicates on an exact captured candidate."""

    def evaluate(self, *, candidate: Candidate) -> tuple[AcceptanceCheckResult, ...]:
        """Return one result per active local check."""
        active = {
            item.id: item
            for item in candidate.content.definitions
            if item.status is DefinitionStatus.APPROVED
        }
        results: list[AcceptanceCheckResult] = []
        for item in active.values():
            if not isinstance(item.body, AcceptanceCheckDefinition):
                continue
            outcome, message = _evaluate_predicate(
                predicate=item.body.predicate, definitions=active
            )
            issues = (
                ()
                if not message
                else (
                    Issue(
                        code=f"acceptance_{outcome.value}",
                        path=("definitions", item.id.value),
                        message=message,
                        severity=IssueSeverity.ERROR
                        if item.body.requirement is CheckRequirement.REQUIRED
                        else IssueSeverity.WARNING,
                    ),
                )
            )
            results.append(
                AcceptanceCheckResult(
                    definition_id=item.id,
                    candidate_hash=candidate.content_hash,
                    evaluator_fingerprint=_EVALUATOR_HASH,
                    outcome=outcome,
                    issues=issues,
                )
            )
        return tuple(results)


class ModelInvariantValidator:
    """Validate captured structure, evidence and reference closure independently."""

    def validate(
        self, *, candidate: Candidate, reference_pack: ReferencePack | None
    ) -> tuple[Issue, ...]:
        """Return explicit diagnostics for the supplied model state."""
        active = candidate.content.definitions
        retired = candidate.content.retired_definitions
        try:
            dependency_index = dependency_definitions(
                scope=candidate.scope,
                bundles=candidate.dependency_bundles,
            )
        except InvalidBundleError as error:
            return tuple(error.issues)
        issues = list(
            validate_model_shapes(
                scope=candidate.scope,
                definitions=(*active, *retired),
                dependencies=dependency_index,
                ontologies=(
                    *(() if reference_pack is None else reference_pack.ontologies),
                    *(
                        closure
                        for archive in dependency_closure(
                            scope=candidate.scope, bundles=candidate.dependency_bundles
                        )
                        if archive.publication.reference_pack is not None
                        for closure in archive.publication.reference_pack.ontologies
                    ),
                ),
            )
        )
        if not active:
            issues.append(
                Issue(
                    code="model_empty",
                    path=("definitions",),
                    message="Review at least one active definition",
                )
            )
        if any(value.status is not DefinitionStatus.APPROVED for value in active) or any(
            value.status is not DefinitionStatus.RETIRED for value in retired
        ):
            issues.append(
                Issue(
                    code="invalid_definition_status",
                    path=("definitions",),
                    message="Materialize active definitions and tombstones in separate inventories",
                )
            )
        if len({value.name for value in (*active, *retired)}) != len(active) + len(retired):
            issues.append(
                Issue(
                    code="duplicate_definition_name",
                    path=("definitions",),
                    message="Keep lookup names unique",
                )
            )
        lineage = [
            item.baseline_definition_id
            for item in (*active, *retired)
            if item.baseline_definition_id is not None
        ]
        baseline = candidate.baseline
        if (
            (baseline is None and lineage)
            or (
                baseline is not None
                and (
                    baseline.scope == candidate.scope
                    or baseline.scope.project_id != candidate.scope.project_id
                )
            )
            or len(set(lineage)) != len(lineage)
            or any(
                (item.origin is DefinitionOrigin.BASELINE)
                != (item.baseline_definition_id is not None)
                for item in (*active, *retired)
            )
        ):
            issues.append(
                Issue(
                    code="invalid_baseline_lineage",
                    path=("baseline",),
                    message="Retain one local correspondence per direct baseline definition.",
                ),
            )
        issues.extend(reference_context_issues(candidate=candidate, pack=reference_pack))
        issues.extend(
            Issue(
                code="source_alignment_stale",
                path=("source_alignments", item.proposal_id.value),
                message="Review the source occurrence against the current definition revision.",
            )
            for item in candidate.content.source_alignments
            if item.disposition is SourceDisposition.STALE
        )
        for value in active:
            if value.basis is EvidenceBasis.DOCUMENTED:
                issues.append(
                    Issue(
                        code="evidence_unavailable",
                        path=("definitions", value.id.value),
                        message="Capture exact source evidence for the documented meaning",
                    )
                )
            elif value.basis is EvidenceBasis.STATEMENT:
                issues.append(
                    Issue(
                        code="confirmation_unavailable",
                        path=("definitions", value.id.value),
                        message="Capture the attributed confirmation for the statement",
                    )
                )
        return tuple(issues)


def _matching_snapshot(
    *,
    candidate: Candidate,
    report: ValidationReport,
    review: ReviewSnapshot,
    validator_fingerprint: str,
) -> bool:
    return (
        report.scope == candidate.scope == review.scope
        and report.candidate_id == candidate.id
        and report.candidate_hash == candidate.content_hash
        and report.reference_pack == candidate.reference_pack
        and report.validator_fingerprint == validator_fingerprint
        and review.version == candidate.review_snapshot_version
        and review.content_hash == candidate.review_snapshot_hash
        and review.decisions == candidate.decisions
        and review.questions == candidate.nonblocking_questions
    )


def _evaluate_results(
    *,
    definitions: Sequence[Definition],
    results: Sequence[AcceptanceCheckResult],
    candidate_hash: ContentHash,
) -> tuple[tuple[ReadinessCheck, ...], tuple[Issue, ...]]:
    captured = {item.definition_id: item for item in results}
    expected = {
        item.id: item.body
        for item in definitions
        if isinstance(item.body, AcceptanceCheckDefinition)
    }
    if (
        len(captured) != len(results)
        or set(expected) != set(captured)
        or any(
            result.candidate_hash != candidate_hash
            or result.evaluator_fingerprint != _EVALUATOR_HASH
            for result in results
        )
    ):
        return (), (
            Issue(
                code="invalid_acceptance_binding",
                path=("acceptance",),
                message="Validate exactly the acceptance definitions in this candidate",
            ),
        )
    checks: list[ReadinessCheck] = []
    blockers: list[Issue] = []
    for identifier, body in expected.items():
        outcome = captured[identifier].outcome
        required = body.requirement is CheckRequirement.REQUIRED
        passed = outcome is CheckOutcome.PASS
        checks.append(
            ReadinessCheck(
                code=f"acceptance_{outcome.value}",
                required=required,
                passed=passed,
                resource_labels=(body.statement.value,),
                message=body.statement.value,
            )
        )
        if required and not passed:
            blockers.append(
                Issue(
                    code=f"acceptance_{outcome.value}",
                    path=("definitions", identifier.value),
                    message="Resolve or explicitly revise the required acceptance check",
                )
            )
    return tuple(checks), tuple(blockers)


class ModelReadinessEvaluator:
    """Decide readiness from explicit captured values."""

    def __init__(self, *, validator_fingerprint: str = VALIDATOR_FINGERPRINT) -> None:
        """Bind the configured validator identity for this preparation."""
        self._validator_fingerprint: str = validator_fingerprint

    def evaluate(
        self,
        *,
        candidate: Candidate,
        validation: ValidationReport,
        reference_pack: ReferencePack | None,
        review: ReviewSnapshot,
        rules: PublicationRules,
    ) -> Readiness:
        """Keep required failures, review gaps and policy visible."""
        checks, acceptance_blockers = _evaluate_results(
            definitions=candidate.content.definitions,
            results=validation.acceptance,
            candidate_hash=candidate.content_hash,
        )
        blockers = [issue for issue in validation.issues if issue.severity is IssueSeverity.ERROR]
        blockers.extend(acceptance_blockers)
        blockers.extend(coverage_blockers(candidate=candidate, pack=reference_pack))
        if not _matching_snapshot(
            candidate=candidate,
            report=validation,
            review=review,
            validator_fingerprint=self._validator_fingerprint,
        ):
            blockers.append(
                Issue(
                    code="snapshot_mismatch",
                    path=("candidate",),
                    message="Validate the exact captured workspace",
                )
            )
        if review.pending_required:
            blockers.append(
                Issue(
                    code="required_review_pending",
                    path=("review",),
                    message="Resolve the remaining required review cases",
                )
            )
        if review.questions and not rules.allow_reviewed_nonblocking_questions:
            blockers.append(
                Issue(
                    code="optional_questions_disallowed",
                    path=("review", "questions"),
                    message="Resolve the optional questions required by this publication policy",
                )
            )
        return Readiness(
            scope=candidate.scope,
            candidate_id=candidate.id,
            candidate_hash=candidate.content_hash,
            ready=not blockers,
            blockers=blockers,
            checks=checks,
            nonblocking_questions=review.questions
            if rules.allow_reviewed_nonblocking_questions
            else (),
        )
