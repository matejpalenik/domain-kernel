"""Explicit PostgreSQL provisioning and a portable recruitment deployment exercise."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel import (
    Accept,
    AttributeDefinition,
    CaseKind,
    CaseStatus,
    Client,
    DomainModelBuilder,
    DomainModelBundle,
    ModelKind,
    ModelNotFoundError,
    ProjectNotFoundError,
    ValueSetDefinition,
    ValueSetType,
)

if TYPE_CHECKING:
    from domain_kernel import ClientConfiguration, Model

POSTGRES_DSN_ENV = "DOMAIN_KERNEL_TOUR_POSTGRES_DSN"
POSTGRES_SCHEMA_ENV = "DOMAIN_KERNEL_TOUR_POSTGRES_SCHEMA"
DEFAULT_SCHEMA = "domain_kernel_tour"


@dataclass(frozen=True, kw_only=True)
class RecruitmentDeployment:
    """Portable release and exact replay evidence from an independent client."""

    release: DomainModelBundle
    reopened_exactly: bool
    replayed_exactly: bool

    @property
    def contract(self) -> tuple[tuple[str, str, str], ...]:
        """Compare the reviewed lookup names, kinds and meanings across backend scopes."""
        return tuple(
            sorted(
                (item.name, item.kind.value, item.meaning)
                for item in self.release.content.definitions
            )
        )


async def deploy_recruitment(
    *, configuration: ClientConfiguration, baseline: DomainModelBundle
) -> RecruitmentDeployment:
    """Review, publish, reopen and retry the same candidate through ordinary SDK calls."""
    client = Client(config=configuration)
    project_name = "recruitment-deployment"
    try:
        project = await client.get_project(name=project_name)
    except ProjectNotFoundError:
        project = await client.create_project(actor="demo:developer", name=project_name)
    model_name = "recruitment-" + baseline.content_hash.value.removeprefix("sha256:")[:16]
    try:
        model = await project.get_model(name=model_name)
    except ModelNotFoundError:
        model = await project.create_model(
            actor="demo:developer",
            name=model_name,
            kind=ModelKind.PROPOSED,
            description="Recruitment contract for an embedding application.",
        )
    await _review_system(model=model, baseline=baseline)
    candidate = await model.prepare_publication(
        actor="demo:developer", idempotency_key="deploy-prepare"
    )
    release = await model.publish(
        actor="demo:publisher",
        publication=candidate,
        version="1.0.0",
        reason="Deliver the reviewed recruitment contract.",
        idempotency_key="deploy-publish",
    )
    restored_project = await Client(config=configuration).get_project(name=project_name)
    restored = await restored_project.get_model(name=model_name)
    replay = await restored.publish(
        actor="demo:publisher",
        publication=candidate,
        version="1.0.0",
        reason="Deliver the reviewed recruitment contract.",
        idempotency_key="deploy-publish",
    )
    archive = await restored.get_version(version="1.0.0")
    return RecruitmentDeployment(
        release=archive,
        reopened_exactly=restored.scope == model.scope
        and archive == release
        and DomainModelBundle.deserialize(payload=archive.serialize()) == release,
        replayed_exactly=replay == release,
    )


async def _review_system(*, model: Model, baseline: DomainModelBundle) -> None:
    source = baseline.get_concept(name="recruitment-ai-system")
    purpose = source.get_attribute(name="intended-purpose")
    reason = "Review the recruitment system and its intended-purpose field."
    cases = await model.list_review_cases(kind=CaseKind.CHANGE_SET)
    case = next((item for item in cases.items if item.reason == reason), None)
    if case is None:
        purpose_type = purpose.value_type
        if not isinstance(purpose_type, ValueSetType):
            raise ValueError("Use the reviewed recruitment-purpose vocabulary.")
        vocabulary = next(
            item
            for item in baseline.content.definitions
            if item.id == purpose_type.value_set and isinstance(item.body, ValueSetDefinition)
        )
        builder = DomainModelBuilder(model_info=model.info)
        local_vocabulary = builder.add_definition(
            name=vocabulary.name,
            display_name=vocabulary.display_name,
            meaning=vocabulary.meaning,
            body=vocabulary.body,
        )
        declared_purpose = AttributeDefinition(
            display_name=purpose.display_name,
            name=purpose.name,
            value_type=ValueSetType(value_set=local_vocabulary),
            required=purpose.required,
            collection=purpose.collection,
            min_items=purpose.min_items,
            max_items=purpose.max_items,
            nullability=purpose.nullability,
            constraints=purpose.constraints,
            terminology=purpose.terminology,
        )
        _ = builder.add_concept(
            name=source.name,
            display_name=source.display_name,
            meaning=source.meaning,
            attributes=[declared_purpose],
        )
        case = await model.propose_change_plan(
            actor="demo:developer", plan=builder.build_change_plan(reason=reason)
        )
    if case.status is CaseStatus.PENDING:
        _ = await model.decide_review(
            actor="demo:reviewer",
            case=case,
            decision=Accept(reason="The field matches the reviewed recruitment vocabulary."),
            idempotency_key="deploy-review",
        )


def main() -> None:
    """Initialize the explicitly selected example schema before starting the notebook."""
    from domain_kernel._database import PostgreSQLSettings, SchemaManager  # noqa: PLC0415

    dsn = os.environ.get(POSTGRES_DSN_ENV)
    if dsn is None:
        message = f"Set {POSTGRES_DSN_ENV} to the disposable PostgreSQL connection URI."
        raise SystemExit(message)
    manager = SchemaManager(
        settings=PostgreSQLSettings(
            dsn=dsn, schema=os.environ.get(POSTGRES_SCHEMA_ENV, DEFAULT_SCHEMA)
        )
    )
    asyncio.run(manager.initialize())


if __name__ == "__main__":
    main()
