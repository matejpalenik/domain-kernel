"""Portable integrity checks over the complete captured publication records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.modeling.domain.validation import ModelInvariantValidator, validator_fingerprint
from domain_kernel.reference_packs.domain.dispositions import coverage_blockers
from domain_kernel.review.domain.decisions import Accept, Reject
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.codecs.record_encoding import record_value
from domain_kernel.shared.domain.enums.check_outcome import CheckOutcome
from domain_kernel.shared.domain.enums.check_requirement import CheckRequirement
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import InvalidBundleError
from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from datetime import datetime

    from domain_kernel.modeling.domain.publications import Approval, Publication
    from domain_kernel.modeling.domain.snapshots import Candidate, DomainModelBundle
    from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.models import DecisionRecord
    from domain_kernel.shared.contracts import ModelScope
    from domain_kernel.shared.identifiers.content_hash import ContentHash


def candidate_digest(*, candidate: Candidate) -> ContentHash:
    """Compute the current semantic candidate hash independently of capture ID."""
    return hash_json(
        value=record_value(
            value=(
                "candidate-v1",
                candidate.scope,
                candidate.kind,
                candidate.description,
                candidate.workspace_revision,
                candidate.reference_pack,
                candidate.baseline,
                candidate.dependencies,
                candidate.content,
                candidate.review_snapshot_version,
                candidate.review_snapshot_hash,
            )
        )
    )


def release_digest(
    *,
    bundle_id: BundleId,
    version: str,
    publication: Publication,
    approval: Approval,
    released_at: datetime,
) -> ContentHash:
    """Hash the semantic release under the fixed v1 format and mapping version."""
    return hash_json(
        value=record_value(
            value=(
                bundle_id,
                publication.scope,
                version,
                publication,
                approval,
                released_at,
            ),
            utc_times=True,
        )
    )


def _diagnostic(*, code: str, message: str) -> Issue:
    return Issue(code=code, path=("publication",), message=message)


def verify_bundle_integrity(*, bundle: DomainModelBundle) -> tuple[Issue, ...]:
    """Verify the root and each materialized dependency without workspace access."""
    issues: list[Issue] = []
    pending = [bundle]
    verified: dict[tuple[ModelScope, str], DomainModelBundle] = {}
    while pending:
        release = pending.pop()
        key = (release.scope, release.version)
        previous = verified.get(key)
        if previous is not None:
            if previous != release:
                issues.append(
                    _diagnostic(
                        code="dependency_substitution",
                        message="Use the same immutable archive wherever a model version appears.",
                    )
                )
            continue
        verified[key] = release
        candidate = release.publication.candidate
        contexts = [candidate.dependency_bundles]
        for record in candidate.decisions:
            if record.dependency_change is not None:
                contexts.extend(
                    (
                        record.dependency_change.before_bundles,
                        record.dependency_change.after_bundles,
                    )
                )
        for context in contexts:
            try:
                pending.extend(dependency_closure(scope=release.scope, bundles=context))
            except InvalidBundleError as error:
                issues.extend(error.issues)
        issues.extend(_verify_publication(publication=release.publication))
        expected = release_digest(
            bundle_id=release.id,
            version=release.version,
            publication=release.publication,
            approval=release.approval,
            released_at=release.published_at,
        )
        if expected != release.content_hash:
            issues.append(
                Issue(
                    code="bundle_hash",
                    path=("content_hash",),
                    message="Retrieve the exact published content.",
                )
            )
    return tuple(issues)


def _verify_publication(*, publication: Publication) -> tuple[Issue, ...]:
    """Verify captured graph and audit bindings without re-running checks."""
    candidate = publication.candidate
    issues = list(
        ModelInvariantValidator().validate(
            candidate=candidate,
            reference_pack=publication.reference_pack,
        )
    )
    issues.extend(coverage_blockers(candidate=candidate, pack=publication.reference_pack))
    if candidate_digest(candidate=candidate) != candidate.content_hash:
        issues.append(
            _diagnostic(code="candidate_hash", message="Use an intact published candidate.")
        )
    if any(issue.severity is IssueSeverity.ERROR for issue in publication.validation.issues):
        issues.append(_diagnostic(code="validation_blocked", message="Use an approved release."))
    fingerprints = publication.validation.semantic_fingerprints
    if fingerprints and publication.validation.validator_fingerprint != validator_fingerprint(
        semantic=fingerprints
    ):
        issues.append(
            _diagnostic(
                code="validator_binding",
                message="Retain the captured semantic validator fingerprints.",
            )
        )
    if not _matching_acceptance(publication=publication):
        issues.append(
            _diagnostic(
                code="acceptance_binding",
                message="Retain the exact recorded acceptance results.",
            )
        )
    if not _matching_decisions(candidate=candidate):
        issues.append(
            _diagnostic(
                code="decision_closure",
                message="Retain the exact attributed review decisions.",
            )
        )
    return tuple(issues)


def _matching_acceptance(*, publication: Publication) -> bool:
    candidate = publication.candidate
    expected = {
        definition.id: definition.body
        for definition in candidate.content.definitions
        if isinstance(definition.body, AcceptanceCheckDefinition)
    }
    results = publication.validation.acceptance
    if tuple(result.definition_id for result in results) != tuple(expected):
        return False
    if len(publication.checks) != len(results):
        return False
    for check, result in zip(publication.checks, results, strict=True):
        body = expected[result.definition_id]
        required = body.requirement is CheckRequirement.REQUIRED
        passed = result.outcome is CheckOutcome.PASS
        if (
            result.candidate_hash != candidate.content_hash
            or check.code != f"acceptance_{result.outcome.value}"
            or check.passed is not passed
            or check.required is not required
            or (required and not passed)
            or check.message != body.statement.value
            or check.resource_labels != (body.statement.value,)
        ):
            return False
    return True


def _matching_decisions(*, candidate: Candidate) -> bool:
    by_id = {record.id: record for record in candidate.decisions}
    if len(by_id) != len(candidate.decisions):
        return False
    if not all(
        set(definition.decision_ids) <= by_id.keys()
        for definition in (*candidate.content.definitions, *candidate.content.retired_definitions)
    ):
        return False
    return all(
        record.scope == candidate.scope
        and record.applied_changes.scope == candidate.scope
        and _dependency_decision(record=record)
        and _decision_edges(record=record, candidate=candidate)
        and _decision_members(record=record, by_id=by_id)
        for record in candidate.decisions
    )


def _dependency_decision(*, record: DecisionRecord) -> bool:
    request = None if record.change_plan is None else record.change_plan.dependency_change
    change = record.dependency_change
    if request is None or change is None:
        return request is None and change is None
    if change.request != request or record.group_decision_id is not None:
        return False
    effects = record.applied_changes
    if isinstance(record.action, Reject):
        return not effects.changes and effects.before_dependencies == effects.after_dependencies
    return (
        isinstance(record.action, Accept)
        and effects.before_dependencies == request.before
        and effects.after_dependencies == request.after
        and {item.id for effect in effects.changes for item in effect.after}
        == set(change.affected_definition_ids)
    )


def _decision_members(*, record: DecisionRecord, by_id: dict[DecisionId, DecisionRecord]) -> bool:
    if record.supersedes_decision_id is not None and record.supersedes_decision_id not in by_id:
        return False
    for member_id in record.member_decision_ids:
        member = by_id.get(member_id)
        if member is None or member.group_decision_id != record.id or member.member_decision_ids:
            return False
    if record.group_decision_id is not None:
        parent = by_id.get(record.group_decision_id)
        return parent is not None and record.id in parent.member_decision_ids
    return True


def _decision_edges(*, record: DecisionRecord, candidate: Candidate) -> bool:
    if record.case_version < 1 or not record.actor.strip():
        return False
    generated = set(record.generated_member_case_ids)
    released = set(record.released_case_ids)
    if generated & released or len(generated) != len(record.generated_member_case_ids):
        return False
    if len(set(record.member_decision_ids)) != len(record.member_decision_ids):
        return False
    if record.change_plan is not None and record.change_plan.scope != candidate.scope:
        return False
    return all(
        definition.scope == candidate.scope
        for change in record.applied_changes.changes
        for definition in (*change.before, *change.after)
    )
