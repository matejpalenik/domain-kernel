from datetime import UTC, datetime

from domain_kernel import ModelId, ModelInfo, ModelKind, ModelScope, ProjectId
from domain_kernel.authoring import DomainModelBuilder


def test_build_keeps_ids_and_creates_detached_plan_revisions() -> None:
    builder = DomainModelBuilder(
        model_info=ModelInfo(
            scope=ModelScope(
                project_id=ProjectId(value="project"), model_id=ModelId(value="model")
            ),
            name="observed",
            display_name="Observed",
            kind=ModelKind.OBSERVED,
            description="Existing.",
            created_at=datetime.now(tz=UTC),
            revision=3,
        )
    )
    _ = builder.add_concept(display_name="Machine", meaning="Physical asset.")
    first = builder.build_change_plan(reason="Start the asset vocabulary.")
    assert builder.build_change_plan(reason=first.reason) == first
    _ = builder.add_concept(display_name="Site", meaning="Physical operating location.")
    second = builder.build_change_plan(reason=first.reason)
    assert second.id != first.id
    assert second.operations[:1] == first.operations
