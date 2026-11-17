"""Exercise manual approval against a reopened SQLite workspace."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    AuditAction,
    AuditRecord,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DefinitionKind,
    ModelKind,
    RelationshipCardinality,
    RelationshipDefinition,
    StaleStateError,
)
from domain_kernel._database import DatabaseSchemaError, SchemaManager, SQLiteSettings
from domain_kernel._shared.infrastructure.sqlite_audit import SQLiteAuditRepository
from domain_kernel.modeling.domain.errors.definition_errors import DefinitionNotFoundError
from domain_kernel.review.domain.decisions import Accept, Reject
from domain_kernel.shared.errors import IdempotencyConflictError

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel.review.domain.models import ReviewCase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_inspected_proposal_and_decision_are_durable_and_replayable(tmp_path: Path) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    client = Client(config=config)
    project = await client.create_project(actor="editor", name="recruitment")
    model = await project.create_model(
        actor="editor",
        name="existing",
        kind=ModelKind.OBSERVED,
        description="Recruitment vocabulary.",
    )
    case = await model.propose_definition(
        actor="editor",
        name="ai-system",
        meaning="The existing AI system.",
        body=ConceptDefinition(),
        reason="Author the initial vocabulary.",
        idempotency_key="proposal",
    )
    assert case.status is CaseStatus.PENDING
    approval = Accept(reason="Approve the inspected definition.")
    preview = await model.preview_changes(case=case, decision=approval)
    assert preview.definition_changes == preview.changes.changes
    assert not preview.blockers
    with pytest.raises(DefinitionNotFoundError):
        _ = await model.get_definition(name="ai-system")
    with pytest.raises(StaleStateError):
        _ = await model.decide_review(
            case=replace(case, reason="Caller modified reason."),
            decision=approval,
            actor="reviewer",
        )
    receipt = await model.decide_review(
        case=case,
        decision=approval,
        actor="reviewer",
        idempotency_key="decision",
    )
    reopened = await Client(config=config).get_project(name=project.name)
    inspected = await reopened.get_model(name=model.info.name)
    concept = await inspected.get_concept(name="ai-system")
    assert concept.id == case.definitions[0].id
    assert concept.decision_ids == (receipt.decision_id,)
    assert (await inspected.get_review_case(case_id=case.id)).status is CaseStatus.RESOLVED
    assert (
        await inspected.decide_review(
            case=case,
            decision=approval,
            actor="reviewer",
            idempotency_key="decision",
        )
        == receipt
    )
    with pytest.raises(IdempotencyConflictError):
        _ = await inspected.decide_review(
            case=case,
            decision=approval,
            actor="other",
            idempotency_key="decision",
        )
    decisions = await inspected.get_review_history(case_id=case.id)
    assert tuple(decision.id for decision in decisions.items) == (receipt.decision_id,)
    revisions = await inspected.get_definition_history(definition_id=concept.id)
    assert revisions.items[0].body == concept.body


async def test_reject_keeps_history_and_releases_only_the_unused_name(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Reality.",
    )

    async def propose() -> ReviewCase:
        return await model.propose_definition(
            actor="editor",
            name="provider",
            meaning="Proposed business meaning.",
            reason="Start with local vocabulary.",
            body=ConceptDefinition(),
        )

    original = await propose()
    rejection = Reject(reason="This formulation is too broad.")
    assert (await model.preview_changes(case=original, decision=rejection)).definition_changes == ()
    _ = await model.decide_review(case=original, decision=rejection, actor="reviewer")
    assert (await model.list_definitions()).items == ()
    replacement = await propose()
    assert replacement.definitions[0].id != original.definitions[0].id
    assert (await model.get_review_history(case_id=original.id)).items[0].action == rejection


async def test_audit_failure_rolls_back_all_review_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing meaning.",
    )
    proposed = await model.propose_definition(
        actor="editor",
        name="provider",
        meaning="The named provider.",
        body=ConceptDefinition(),
        reason="Introduce the actor for review.",
    )
    action = Accept(reason="Approve the inspected actor.")
    append = SQLiteAuditRepository.append

    async def fail_audit(repository: SQLiteAuditRepository, *, record: AuditRecord) -> None:
        if record.action is AuditAction.DECIDE_REVIEW:
            raise RuntimeError("injected audit failure")
        await append(repository, record=record)

    with monkeypatch.context() as replacement:
        replacement.setattr(SQLiteAuditRepository, "append", fail_audit)
        with pytest.raises(RuntimeError, match="injected audit failure"):
            _ = await model.decide_review(
                actor="reviewer",
                case=proposed,
                decision=action,
                idempotency_key="review-actor",
            )

    assert (await model.list_definitions()).items == ()
    assert (await model.get_review_history(case_id=proposed.id)).items == ()
    assert await model.get_review_case(case_id=proposed.id) == proposed
    assert (await project.get_model(name=model.info.name)).info.revision == model.info.revision
    retry = await model.decide_review(
        actor="reviewer",
        case=proposed,
        decision=action,
        idempotency_key="review-actor",
    )
    assert retry.workspace_revision == model.info.revision + 1


@pytest.mark.parametrize("prior", ["1", "9"])
async def test_explicit_schema_upgrade_preserves_existing_workspace(
    tmp_path: Path, prior: str
) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    original = await Client(config=config).create_project(actor="editor", name="existing")
    path = tmp_path / ".domain-kernel/state.sqlite3"

    def prepare_prior_schema() -> None:
        with closing(sqlite3.connect(database=path)) as connection, connection:
            _ = connection.execute("DROP TABLE dk_source_document")
            if prior == "1":
                for sql in (
                    "DROP TABLE dk_source_parsed_payload",
                    "DROP TABLE dk_source_evidence",
                    "DROP TABLE dk_source_copy_intent",
                    "DROP TABLE dk_source_manifest_entry",
                    "DROP TABLE dk_source_manifest",
                    "DROP TABLE dk_source_ingestion",
                    "DROP TABLE dk_source_revision",
                    "DROP TABLE dk_source",
                    "DROP TABLE dk_model_baseline",
                    "DROP TABLE dk_model_dependency",
                    "DROP TABLE dk_model_pack_selection",
                    "DROP TABLE dk_bundle",
                    "DROP TABLE dk_publication",
                    "DROP TABLE dk_validation_report",
                    "DROP TABLE dk_candidate",
                    "DROP TABLE dk_decision",
                    "DROP TABLE dk_review_case_version",
                    "DROP TABLE dk_review_case",
                    "DROP TABLE dk_definition_revision",
                    "DROP TABLE dk_definition",
                ):
                    _ = connection.execute(sql)
            _ = connection.execute("UPDATE dk_schema SET version = ?", (prior,))

    await asyncio.to_thread(prepare_prior_schema)
    client = Client(config=config)
    with pytest.raises(DatabaseSchemaError, match="compatible"):
        _ = await client.get_project(name="existing")
    await SchemaManager(settings=SQLiteSettings(path=path)).upgrade(target_version="10")
    reopened = await client.get_project(name="existing")
    assert reopened.id == original.id
    assert len((await reopened.get_audit_history()).items) == 1


async def test_typed_relationship_lookup_restores_the_inspected_concept_ids(tmp_path: Path) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor",
        name="recruitment",
    )
    model = await project.create_model(
        actor="editor",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing meaning.",
    )
    concept_case = await model.propose_definition(
        actor="editor",
        name="provider",
        meaning="Provider in the recruitment context.",
        body=ConceptDefinition(),
        reason="Introduce an inspected actor.",
    )
    approval = Accept(reason="Approve the inspected relationship or concept.")
    _ = await model.decide_review(case=concept_case, decision=approval, actor="reviewer")
    provider = await model.get_concept(name="provider")
    relationship = RelationshipDefinition(
        source_concept_id=provider.id,
        target_concept_id=provider.id,
        cardinality=RelationshipCardinality.many_to_many(),
    )
    case = await model.propose_definition(
        actor="editor",
        name="works-with",
        meaning="Providers can work with other providers.",
        body=relationship,
        reason="Record a relationship between providers.",
    )
    _ = await model.decide_review(case=case, decision=approval, actor="reviewer")
    loaded = await model.get_relationship(name="works-with")
    assert loaded.body == relationship
    assert loaded.kind is DefinitionKind.RELATIONSHIP
