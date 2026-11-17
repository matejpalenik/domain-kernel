"""Run the pinned recruitment model through manual review and independent consumption."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from domain_kernel import (
    Accept,
    AcceptanceCheckDefinition,
    AttributeDefinition,
    BusinessCode,
    CheckRequirement,
    CollectionKind,
    ContentHash,
    Count,
    Definition,
    DistinctDefinitionsCheck,
    DomainModelBuilder,
    DomainModelBundle,
    KeyDefinition,
    LabelText,
    LanguageTag,
    LocalizedLabel,
    MeaningText,
    ModelKind,
    RelationshipCardinality,
    Terminology,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from domain_kernel import DefinitionId, Model, ModelChangePlan
    from domain_kernel.shared.hashing import JsonValue

SOURCE_MANIFEST = Path(__file__).with_name("notebooks") / "fixtures" / "sources.json"
INITIAL_MAXIMUM = Count(value=2)
REVIEWED_MAXIMUM = Count(value=3)


def _edition(*, source_id: str) -> dict[str, JsonValue]:
    entries: JsonValue = json.loads(SOURCE_MANIFEST.read_bytes())  # pyright: ignore[reportAny]
    if isinstance(entries, Sequence) and not isinstance(entries, str):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == source_id:
                return entry
    raise ValueError("Restore the verified AI Act edition in the teaching manifest")


def verified_provider_terminology() -> Terminology:
    """Use the provider labels verified from the exact original editions."""
    french = next(
        (
            text
            for passage in _french_passages()
            if isinstance(passage, dict)
            and passage.get("id") == "ai-fr-3"
            and type(text := passage.get("text")) is str
        ),
        "",
    )
    if "fournisseur" not in french.split("; "):
        raise ValueError("Restore the verified French Article 3 provider label")
    return Terminology(
        labels=[
            LocalizedLabel(language=LanguageTag(value="en"), text=LabelText(value="Provider")),
            LocalizedLabel(language=LanguageTag(value="fr"), text=LabelText(value="fournisseur")),
        ],
    )


def _french_passages() -> Sequence[JsonValue]:
    passages = _edition(source_id="ai-act-fr").get("passages")
    if not isinstance(passages, Sequence) or isinstance(passages, str):
        raise TypeError("Restore the verified French article passages")
    return passages


def add_recruitment_purposes(*, builder: DomainModelBuilder) -> DefinitionId:
    """Author the closed list of purposes supported by the example application."""
    return builder.add_value_set(
        name="recruitment-purpose",
        meaning="Application choices for recording how a system is used in recruitment.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="screen"),
                label=LabelText(value="Screen applications"),
                meaning=MeaningText(value="Screen and filter incoming applications."),
            ),
            ValueSetMember(
                code=BusinessCode(value="evaluate"),
                label=LabelText(value="Evaluate candidates"),
                meaning=MeaningText(value="Evaluate candidates for a role."),
            ),
            ValueSetMember(
                code=BusinessCode(value="rank"),
                label=LabelText(value="Rank candidates"),
                meaning=MeaningText(value="Order candidates for review by the recruitment team."),
            ),
        ],
    )


def system_fields(
    *,
    purposes: DefinitionId,
) -> tuple[tuple[AttributeDefinition, ...], KeyDefinition]:
    """Author a system identifier and an optional bounded selection of purposes."""
    identifier = AttributeDefinition.string(name="system-code", required=True)
    return (
        (
            identifier,
            AttributeDefinition.value_set(
                name="intended-purpose",
                value_set=purposes,
                collection=CollectionKind.SET,
                max_items=INITIAL_MAXIMUM,
            ),
        ),
        KeyDefinition(name="system-identity", attributes=[identifier.id]),
    )


def add_actor_check(
    *,
    builder: DomainModelBuilder,
    provider: Definition | DefinitionId,
    deployer: Definition | DefinitionId,
) -> None:
    """Check that the system contract distinguishes the two reviewed actor definitions."""
    references = tuple(value for value in (provider, deployer) if isinstance(value, Definition))
    _ = builder.add_definition(
        name="distinct-actor-definitions",
        meaning="Keep separate definitions for provider and deployer responsibilities.",
        body=AcceptanceCheckDefinition(
            statement=MeaningText(value="The reviewed provider and deployer IDs are distinct."),
            requirement=CheckRequirement.REQUIRED,
            predicate=DistinctDefinitionsCheck(
                left=provider.id if isinstance(provider, Definition) else provider,
                right=deployer.id if isinstance(deployer, Definition) else deployer,
            ),
        ),
        referenced_definitions=references,
    )


async def _review(*, model: Model, plan: ModelChangePlan) -> None:
    case = await model.propose_change_plan(actor="demo:developer", plan=plan)
    decision = Accept(reason=plan.reason)
    impact = await model.preview_changes(case=case, decision=decision)
    if not impact.definition_changes:
        raise RuntimeError("Inspect the recruitment changes before recording the sample decision")
    # The sample reviewer authorizes this fixture. A host supplies its own reviewer and decision.
    _ = await model.decide_review(actor="demo:reviewer", case=case, decision=decision)


async def _release(*, model: Model, version: str, reason: str) -> DomainModelBundle:
    prepared = await model.prepare_publication(actor="demo:developer")
    inspected = await model.get_publication(publication_id=prepared.id)
    return await model.publish(
        publication=inspected,
        version=version,
        actor="demo:publisher",
        reason=reason,
    )


async def author_releases(*, workspace: Path) -> tuple[DomainModelBundle, DomainModelBundle]:
    """Build and revise the small recruitment model in an isolated new workspace."""
    from domain_kernel import Client, ClientConfiguration  # noqa: PLC0415 - Producer only.

    english = _edition(source_id="ai-act-en")
    pin = english.get("sha256")
    if type(pin) is not str:
        raise ValueError("Restore the verified English AI Act digest")
    source_hash = ContentHash(value=f"sha256:{pin}")
    project = await Client(config=ClientConfiguration(base_dir=workspace)).create_project(
        actor="demo:developer",
        name="recruitment-legislation",
    )
    model = await project.create_model(
        actor="demo:developer",
        name="ai-in-recruitment",
        kind=ModelKind.OBSERVED,
        description=(
            f"Recruitment and selection in the original English AI Act ({source_hash.value})."
        ),
    )
    builder = DomainModelBuilder(model_info=model.info)
    fields, key = system_fields(purposes=add_recruitment_purposes(builder=builder))
    system = builder.add_concept(
        name="recruitment-ai-system",
        meaning="An AI system used to screen applications or evaluate candidates.",
        attributes=fields,
        keys=[key],
    )
    provider = builder.add_concept(
        name="ai-provider",
        meaning="An actor making a developed or commissioned AI system available under its name.",
        terminology=verified_provider_terminology(),
    )
    deployer = builder.add_concept(
        name="ai-deployer",
        meaning="An actor using an AI system under its authority in a professional context.",
    )
    _ = builder.add_relationship(
        name="provides",
        meaning="The provider makes the recruitment system available.",
        source=provider,
        target=system,
        cardinality=RelationshipCardinality.many_to_many(),
    )
    _ = builder.add_relationship(
        name="uses",
        meaning="The deployer uses the recruitment system.",
        source=deployer,
        target=system,
        cardinality=RelationshipCardinality.many_to_many(),
    )
    add_actor_check(builder=builder, provider=provider, deployer=deployer)
    await _review(
        model=model, plan=builder.build_change_plan(reason="Review the recruitment contract.")
    )
    first = await _release(
        model=model, version="1.0.0", reason="Release the first reviewed contract."
    )

    reopened = await project.get_model(name=model.info.name)
    inspected_system = await reopened.get_concept(concept_id=system)
    correction = DomainModelBuilder(model_info=reopened.info)
    correction.edit_attribute(
        concept=inspected_system,
        attribute=inspected_system.get_attribute(name="intended-purpose"),
        max_items=REVIEWED_MAXIMUM,
    )
    await _review(
        model=reopened,
        plan=correction.build_change_plan(
            reason="Allow recording all three selected application purposes."
        ),
    )
    second = await _release(
        model=reopened,
        version="1.1.0",
        reason="Release the reviewed purpose bound correction.",
    )
    if await reopened.get_version(version=first.version) != first:
        raise RuntimeError("The first release must remain unchanged")
    return first, second


def read_release(*, payload: bytes | str) -> DomainModelBundle:
    """Validate a portable release without access to the producing workspace."""
    return DomainModelBundle.deserialize(payload=payload)


def inspect_transferred_releases(*, payloads: Sequence[bytes]) -> str:
    """Inspect the exact files and hashes in a fresh consumer with no producer database."""
    return _inspect_delivery(
        payloads=payloads,
        inspect_code="""
    system = bundle.get_concept(name="recruitment-ai-system")
    purposes = system.get_attribute(name="intended-purpose")
    print(f"Received version: {bundle.version}")
    print(f"Reviewed concept: {system.name}")
    print(f"Recorded publisher: {bundle.approval.actor}")
    print(f"Purpose maximum: {purposes.max_items.value}")
""",
    )


def inspect_transferred_dependencies(*, payload: bytes) -> str:
    """Read the exact inherited legal and AI meanings in the delivered recruitment archive."""
    return _inspect_delivery(
        payloads=[payload],
        inspect_code="""
    legislative, regulation = bundle.publication.candidate.dependency_bundles
    legal_resource = legislative.get_concept(name="legal-resource")
    general_system = regulation.get_concept(name="ai-system")
    local_system = bundle.get_concept(name="recruitment-ai-system")
    inherited = local_system.get_attribute(name="general-ai-meaning").value_type.concept
    assert inherited.model == regulation.model_version
    assert inherited.definition_id == general_system.id
    assert inherited.definition_revision == general_system.revision
    assert regulation.publication.candidate.dependency_bundles == (legislative,)
    assert local_system.id != general_system.id
    print(f"Offline legal meaning: {legal_resource.name} @ {legislative.version}")
    print(f"Offline general AI meaning: {general_system.name} @ {regulation.version}")
    print(f"Retained separate recruitment identity: {local_system.id != general_system.id}")
""",
    )


def _inspect_delivery(*, payloads: Sequence[bytes], inspect_code: str) -> str:
    consumer_script = (
        """
from pathlib import Path
import sys

from domain_kernel import ContentHash, DomainModelBundle

def require_offline(event, _args):
    if event in {"socket.connect", "sqlite3.connect"}:
        raise RuntimeError("Consumer execution has no network or database access")

sys.addaudithook(require_offline)
for file_name, transport_hash in zip(sys.argv[1::2], sys.argv[2::2], strict=True):
    bundle = DomainModelBundle.deserialize(
        payload=Path(file_name).read_bytes(), expected_hash=ContentHash(value=transport_hash),
    )
"""
        + inspect_code
    )
    with TemporaryDirectory(prefix="recruitment-delivery-") as delivery:
        arguments = [sys.executable, "-I", "-c", consumer_script]
        for number, payload in enumerate(payloads, start=1):
            file_name = f"release-{number}.bundle.json"
            _ = (Path(delivery) / file_name).write_bytes(payload)
            arguments.extend([file_name, hash_bytes(content=payload).value])
        result = subprocess.run(  # noqa: S603 - Current interpreter and fixed consumer code.
            arguments,
            cwd=delivery,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    return result.stdout


def main() -> None:
    """Run the example with ephemeral producer and consumer state."""
    with TemporaryDirectory(prefix="recruitment-producer-") as workspace:
        first, second = asyncio.run(author_releases(workspace=Path(workspace)))
        _ = sys.stdout.write(
            inspect_transferred_releases(
                payloads=[first.serialize(), second.serialize()],
            )
        )


if __name__ == "__main__":
    main()
