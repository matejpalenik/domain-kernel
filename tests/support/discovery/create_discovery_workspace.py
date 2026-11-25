"""Create a model workspace with a pinned source for discovery tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel import (
    Client,
    ClientConfiguration,
    ModelKind,
    Person,
    PersonId,
    Statement,
    StatementForm,
    StatementIntent,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, ModelGateway, SourceRevision


DISCOVERY_STATEMENT = "This code locates a provision in our recruitment application."


async def create_discovery_workspace(
    *,
    path: Path,
    gateway: ModelGateway | None,
) -> tuple[Model, SourceRevision]:
    """Create a model workspace and capture the test statement as a source."""
    project = await Client(
        config=ClientConfiguration(
            base_dir=path,
            model_gateway=gateway,
        )
    ).create_project(actor="editor", name="recruitment")
    statement = await project.ingest_source(
        actor="editor",
        name="application-code-interview",
        source=Statement(
            text=DISCOVERY_STATEMENT,
            speaker=Person(id=PersonId(value="developer"), name="Ari", role="Developer"),
            context="Application codes",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor",
        name="locators",
        kind=ModelKind.PROPOSED,
        description="The application needs internal lookup codes.",
    )
    return model, statement.revision
