from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain_kernel import ContentHash, ModelId, ProjectId
from domain_kernel.shared.domain.audit import (
    Artifact,
    AuditAction,
    AuditOutcome,
    AuditRecord,
    AuditResource,
)
from domain_kernel.shared.identifiers.audit_id import AuditId


def _record() -> AuditRecord:
    return AuditRecord(
        id=AuditId(value="audit"),
        project_id=ProjectId(value="project"),
        model_id=ModelId(value="model"),
        action=AuditAction.DECIDE_REVIEW,
        outcome=AuditOutcome.SUCCEEDED,
        actor="editor",
        recorded_at=datetime.now(tz=UTC),
        before=[],
        after=[],
    )


def test_audit_detaches_exact_historical_resources() -> None:
    original = _record()
    resource = AuditResource(
        resource_id=ModelId(value="model"),
        revision=1,
        content_hash=ContentHash(value=f"sha256:{'a' * 64}"),
    )
    after = [resource]
    record = replace(original, after=after)
    after.clear()
    assert record.after == (resource,)


def test_audit_requires_attributed_and_scoped_effects() -> None:
    original = _record()
    outside = Artifact(
        project_id=ProjectId(value="outside"),
        model_id=original.model_id,
        store="exports",
        key="model.json",
        content_hash=ContentHash(value=f"sha256:{'a' * 64}"),
    )

    with pytest.raises(ValueError, match="Actor"):
        _ = replace(original, actor=" ")
    with pytest.raises(ValueError, match="scope"):
        _ = replace(original, after=[outside])
    with pytest.raises(ValueError, match="time zone"):
        _ = replace(original, recorded_at=original.recorded_at.replace(tzinfo=None))
