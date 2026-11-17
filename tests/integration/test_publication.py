"""Verify reviewed releases across independent workspace handles."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AuditAction,
    Client,
    ConceptDefinition,
    IdempotencyConflictError,
    ModelKind,
    PublicationBlockedError,
    StaleStateError,
)
from domain_kernel._shared.infrastructure.sqlite_audit import SQLiteAuditRepository
from domain_kernel.configuration import PublicationPolicy
from domain_kernel.shared.errors import ScopeMismatchError, VersionExistsError

if TYPE_CHECKING:
    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel.modeling.api.model import Model
    from tests.integration.conftest import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _review_concept(*, model: Model, name: str) -> None:
    case = await model.propose_definition(
        actor="author",
        name=name,
        meaning="A role in recruitment.",
        body=ConceptDefinition(),
        reason="Add a recruitment role.",
    )
    _ = await model.decide_review(
        actor="reviewer",
        case=case,
        decision=Accept(reason="Role agreed."),
    )


async def test_preparation_and_exact_releases_replay_across_clients(
    database_backend: DatabaseBackend,
) -> None:
    config = database_backend.config
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Recruitment.",
    )
    case = await model.propose_definition(
        actor="author",
        name="provider",
        meaning="The provider.",
        body=ConceptDefinition(),
        reason="Review the provider role.",
    )
    with pytest.raises(PublicationBlockedError) as caught:
        _ = await model.prepare_publication(actor="editor", idempotency_key="blocked")
    blocked = caught.value.publication
    assert blocked is not None
    assert caught.value.issues is blocked.blockers
    assert not blocked.ready
    assert (await model.list_publications()).items == (blocked,)
    assert await model.get_publication(publication_id=blocked.id) == blocked
    with pytest.raises(PublicationBlockedError):
        _ = await model.publish(
            publication=blocked,
            version="1.0.0",
            actor="owner",
            reason="Release.",
        )

    _ = await model.decide_review(
        actor="reviewer",
        case=case,
        decision=Accept(reason="Provider agreed."),
    )
    reopened_project = await Client(config=config).get_project(name=project.name)
    reopened = await reopened_project.get_model(name=model.info.name)
    with pytest.raises(PublicationBlockedError) as replay:
        _ = await reopened.prepare_publication(actor="editor", idempotency_key="blocked")
    assert replay.value.publication == blocked
    prepared = await reopened.prepare_publication(actor="editor", idempotency_key="ready")
    assert prepared.ready
    assert (await model.list_versions()).items == ()
    inspected = await model.get_publication(publication_id=prepared.id)
    first = await model.publish(
        publication=inspected,
        version="1.0.0",
        actor="owner",
        reason="Release.",
        idempotency_key="first",
    )
    assert first.approval.actor == "owner"
    assert first.approval.reason == "Release."
    assert first.approval.candidate_hash == prepared.candidate.content_hash
    assert first.publication == inspected

    await _review_concept(model=reopened, name="deployer")
    assert await model.prepare_publication(actor="editor", idempotency_key="ready") == prepared
    assert (
        await reopened.publish(
            publication=prepared,
            version="1.0.0",
            actor="owner",
            reason="Release.",
            idempotency_key="first",
        )
        == first
    )
    with pytest.raises(IdempotencyConflictError):
        _ = await reopened.publish(
            publication=prepared,
            version="1.0.0",
            actor="other",
            reason="Release.",
            idempotency_key="first",
        )
    with pytest.raises(StaleStateError):
        _ = await reopened.publish(
            publication=prepared,
            version="1.1.0",
            actor="owner",
            reason="Release.",
        )
    revised = await reopened.prepare_publication(actor="editor")
    with pytest.raises(VersionExistsError):
        _ = await reopened.publish(
            publication=revised,
            version="1.0.0",
            actor="owner",
            reason="Duplicate.",
        )
    second = await reopened.publish(
        publication=revised,
        version="1.1.0",
        actor="owner",
        reason="Release the deployer.",
    )
    assert await reopened.get_version(version="1.0.0") == first
    page = await model.list_versions(limit=1)
    assert page.items == (first,)
    assert page.next_cursor is not None
    assert (await model.list_versions(limit=1, cursor=page.next_cursor)).items == (second,)
    audit = await model.get_audit_history()
    assert tuple(item.actor for item in audit.items if item.action is AuditAction.PUBLISH) == (
        "owner",
        "owner",
    )
    assert await model.diff(before=first, after=second) == await model.diff(
        before=first.model_version,
        after=second.model_version,
    )
    assert await model.diff(before=first.model_version, after=revised.candidate) == revised.changes
    assert await model.get_audit_history() == audit


async def test_concurrent_publication_claims_one_version(database_backend: DatabaseBackend) -> None:
    project = await Client(config=database_backend.config).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="observed",
        description="Recruitment.",
    )
    foreign = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="foreign",
        description="Separate model.",
    )
    await _review_concept(model=model, name="actor")
    prepared = await model.prepare_publication(actor="editor")
    with pytest.raises(ScopeMismatchError):
        _ = await foreign.publish(
            publication=prepared,
            version="1",
            actor="owner",
            reason="Wrong scope.",
        )

    async def release(*, actor: str) -> bool:
        try:
            _ = await model.publish(
                publication=prepared, version="1", actor=actor, reason="Release."
            )
        except VersionExistsError:
            return False
        return True

    outcomes = await asyncio.gather(release(actor="owner"), release(actor="delegate"))
    assert sorted(outcomes) == [False, True]
    assert len((await model.list_versions()).items) == 1


async def test_publishing_rechecks_policy_and_rolls_back_failed_audit(
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = database_backend.config
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="observed",
        description="Recruitment.",
    )
    await _review_concept(model=model, name="actor")
    prepared = await model.prepare_publication(actor="editor")
    policy_project = await Client(
        config=config.model_copy(
            update={"publication": PublicationPolicy(allow_reviewed_nonblocking_questions=False)}
        )
    ).get_project(name=project.name)
    policy_model = await policy_project.get_model(name=model.info.name)
    with pytest.raises(StaleStateError):
        _ = await policy_model.publish(
            publication=prepared,
            version="1",
            actor="owner",
            reason="Release.",
        )
    with pytest.raises(StaleStateError):
        _ = await model.publish(
            publication=replace(prepared, policy_fingerprint="forged"),
            version="1",
            actor="owner",
            reason="Release.",
        )

    async def fail_append(_self: SQLiteAuditRepository, *, record: AuditRecord) -> None:
        assert record.action is AuditAction.PUBLISH
        raise RuntimeError("Simulated write failure")

    audit = await model.get_audit_history()
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteAuditRepository, "append", fail_append)
        with pytest.raises(RuntimeError, match="Simulated write failure"):
            _ = await model.publish(
                publication=prepared,
                version="1",
                actor="owner",
                reason="Release.",
                idempotency_key="release",
            )
    assert await model.get_audit_history() == audit
    assert (await model.list_versions()).items == ()
    bundle = await model.publish(
        publication=prepared,
        version="1",
        actor="owner",
        reason="Release.",
        idempotency_key="release",
    )
    assert bundle.approval.publication_id == prepared.id
