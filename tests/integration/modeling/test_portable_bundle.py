"""Exercise complete portable releases through the public API."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from domain_kernel import (
    Accept,
    AttributeDefinition,
    BusinessCode,
    Client,
    ClientConfiguration,
    CollectionKind,
    ConceptDefinition,
    Count,
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
    DefinitionStatus,
    DomainModelBuilder,
    DomainModelBundle,
    InvalidBundleError,
    KeyDefinition,
    LabelText,
    MeaningText,
    ModelKind,
    StaleStateError,
    UnsupportedBundleVersionError,
    ValueSetMember,
    ValueSetMembership,
    validate_bundle,
)
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel.shared.hashing import JsonValue

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def published(tmp_path: Path) -> DomainModelBundle:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        kind=ModelKind.OBSERVED,
        name="observed",
        description="Reviewed recruitment definitions.",
    )
    actor_key = AttributeDefinition.string(name="identifier", required=True)
    contacts = AttributeDefinition.string(
        name="contacts",
        collection=CollectionKind.LIST,
        max_items=Count(value=3),
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_definition(
        name="actor",
        meaning="A role in recruitment.",
        body=ConceptDefinition(
            attributes=[actor_key, contacts],
            keys=[KeyDefinition(name="identity", attributes=[actor_key.id])],
        ),
    )
    hour = builder.add_unit(name="hour", meaning="Local hour.", symbol="h")
    units = builder.add_value_set(
        name="duration-units",
        meaning="Reviewed duration units.",
        membership=ValueSetMembership.CLOSED,
        members=[
            ValueSetMember(
                code=BusinessCode(value="h"),
                label=LabelText(value="Hour"),
                meaning=MeaningText(value="A local duration unit."),
                unit=hour,
            )
        ],
    )
    _ = builder.add_quantity(name="duration", meaning="Processing duration.", units=units)
    plan = builder.build_change_plan(reason="Review local identity and optional contacts.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    prepared = await model.prepare_publication(actor="editor")
    return await model.publish(
        publication=prepared,
        version="1.0.0",
        actor="publisher",
        reason="Release.",
    )


async def test_bundle_round_trip_uses_only_core_types(
    published: DomainModelBundle,
    tmp_path: Path,
) -> None:
    canonical = published.serialize()
    loaded = DomainModelBundle.deserialize(
        payload=canonical.decode("utf-8"),
        expected_hash=hash_bytes(content=canonical),
    )
    assert loaded == published
    assert loaded.serialize() == canonical
    original = published.get_concept(name="actor")
    restored = loaded.get_concept(concept_id=original.id)
    assert restored == original
    assert restored.get_key(name="identity").attributes == (
        original.get_attribute(name="identifier").id,
    )
    assert restored.get_attribute(name="contacts").max_items == Count(value=3)
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys\n"
                "from domain_kernel import DomainModelBundle\n"
                "bundle = DomainModelBundle.deserialize(payload=sys.stdin.buffer.read())\n"
                "assert 'sqlalchemy' not in sys.modules and 'pydantic' not in sys.modules\n"
                "print(bundle.get_concept(name='actor').get_key(name='identity').name)\n"
            ),
        ],
        cwd=tmp_path,
        input=canonical,
        capture_output=True,
        check=True,
    )
    assert result.stdout == b"identity\n"


def _json(*, payload: bytes | str) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = json.loads(payload)  # pyright: ignore[reportAny]
    return result


async def test_bundle_wire_is_closed_and_keeps_explicit_bounds(
    published: DomainModelBundle,
) -> None:
    doc = _json(payload=published.serialize())
    assert doc["format"] == "domain-kernel.bundle"
    assert doc["schema_version"] == "1.0"
    publication = doc["publication"]
    assert isinstance(publication, dict)
    candidate = publication["candidate"]
    assert isinstance(candidate, dict)
    content = candidate["content"]
    assert isinstance(content, dict)
    definitions = content["definitions"]
    assert isinstance(definitions, Sequence)
    definition = definitions[0]
    assert isinstance(definition, dict)
    body = definition["body"]
    assert isinstance(body, dict)
    attributes = body["attributes"]
    assert isinstance(attributes, Sequence)
    first, second = attributes
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert (
        first["id"] == published.get_concept(name="actor").get_attribute(name="identifier").id.value
    )
    assert first["min_items"] is None
    assert first["max_items"] is None
    assert (second["min_items"], second["max_items"]) == (0, 3)
    schema = _json(payload=DomainModelBundle.get_json_schema())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert (
        DomainModelBundle.get_json_schema(schema_version="1.0")
        == DomainModelBundle.get_json_schema()
    )


async def test_transport_and_content_hash_check_different_inputs(
    published: DomainModelBundle,
) -> None:
    payload = published.serialize()
    formatted = json.dumps(_json(payload=payload), indent=2)
    assert DomainModelBundle.deserialize(payload=formatted) == published
    with pytest.raises(InvalidBundleError) as mismatch:
        _ = DomainModelBundle.deserialize(
            payload=formatted, expected_hash=hash_bytes(content=payload)
        )
    assert mismatch.value.issues[0].code == "transport_hash"

    payload_doc = _json(payload=payload)
    payload_doc["version"] = "different"
    with pytest.raises(InvalidBundleError) as changed:
        _ = DomainModelBundle.deserialize(payload=json.dumps(payload_doc))
    assert changed.value.issues[0].code == "bundle_hash"

    modified = replace(published, content_hash=hash_bytes(content=b"tampered"))
    assert not validate_bundle(bundle=modified).valid
    with pytest.raises(InvalidBundleError):
        _ = modified.serialize()


async def test_bundle_decoder_rejects_limits_versions_duplicates_and_legacy_fields(
    published: DomainModelBundle,
) -> None:
    payload = published.serialize()
    with pytest.raises(InvalidBundleError) as limit:
        _ = DomainModelBundle.deserialize(payload=payload, max_bytes=len(payload) - 1)
    assert limit.value.issues[0].code == "bundle_size"
    with pytest.raises(InvalidBundleError):
        _ = DomainModelBundle.deserialize(payload=b'{"x":' + b"[" * 70 + b"null" + b"]" * 70 + b"}")
    with pytest.raises(InvalidBundleError):
        _ = DomainModelBundle.deserialize(payload=b'{"format":null,' + payload[1:])
    with pytest.raises(InvalidBundleError):
        _ = DomainModelBundle.deserialize(
            payload=payload.replace(b'"min_items":', b'"minimum":', 1)
        )
    with pytest.raises(InvalidBundleError):
        _ = DomainModelBundle.deserialize(
            payload=payload.replace(b'"min_items":0', b'"min_items":null', 1)
        )
    with pytest.raises(InvalidBundleError):
        _ = DomainModelBundle.deserialize(
            payload=payload.replace(b'"required":false', b'"required":0', 1)
        )
    with pytest.raises(UnsupportedBundleVersionError):
        _ = DomainModelBundle.deserialize(
            payload=payload.replace(b'"schema_version":"1.0"', b'"schema_version":"2.0"')
        )
    with pytest.raises(UnsupportedBundleVersionError):
        _ = DomainModelBundle.get_json_schema(schema_version=published.version)


async def test_detached_bundles_must_match_the_registered_release(
    published: DomainModelBundle,
    tmp_path: Path,
) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    project = await Client(config=config).get_project(name="recruitment")
    model = await project.get_model(name="observed")
    loaded = DomainModelBundle.deserialize(payload=published.serialize())
    with pytest.raises(DefinitionNotFoundError):
        _ = loaded.get_concept(name="absent")
    with pytest.raises(DefinitionKindMismatchError):
        _ = loaded.get_concept(name="hour")
    with pytest.raises(ValueError, match="exactly one"):
        _ = loaded.get_concept(name="actor", concept_id=loaded.get_concept(name="actor").id)
    changes = await model.diff(before=loaded, after=published.model_version)
    assert not changes.changes
    altered = DomainModelBundle.from_approved(
        publication=loaded.publication,
        approval=replace(loaded.approval, reason="An unregistered reason."),
        bundle_id=loaded.id,
        version=loaded.version,
        now=loaded.published_at,
    )
    with pytest.raises(StaleStateError):
        _ = await model.diff(before=altered, after=published)
    with pytest.raises(InvalidBundleError):
        _ = await model.diff(
            before=replace(altered, content_hash=loaded.content_hash), after=loaded
        )


async def test_retired_concept_retains_exact_children_in_later_bundle(
    published: DomainModelBundle,
    tmp_path: Path,
) -> None:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name="recruitment",
    )
    model = await project.get_model(name="observed")
    actor = await model.get_definition(name="actor")
    builder = DomainModelBuilder(model_info=model.info)
    builder.remove_definition(definition=actor)
    plan = builder.build_change_plan(reason="Retain the prior actor as a retired concept.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    ready = await model.prepare_publication(actor="editor")
    newer = await model.publish(
        publication=ready,
        version="1.1.0",
        actor="publisher",
        reason="Release retirement.",
    )
    previous = DomainModelBundle.deserialize(payload=published.serialize()).get_concept(
        name="actor"
    )
    retired = DomainModelBundle.deserialize(payload=newer.serialize()).get_concept(
        concept_id=actor.id
    )
    assert retired.id == previous.id
    assert retired.status is DefinitionStatus.RETIRED
    assert previous.status is DefinitionStatus.APPROVED
    assert retired.revision == previous.revision + 1
    assert retired.attributes == previous.attributes
    assert retired.keys == previous.keys


async def test_content_closure_and_approval_are_verified(published: DomainModelBundle) -> None:
    preparation = published.publication
    candidate = preparation.candidate
    contents = replace(
        candidate.content,
        definitions=tuple(item for item in candidate.content.definitions if item.name != "hour"),
    )
    detached = DomainModelBundle.from_approved(
        publication=replace(preparation, candidate=replace(candidate, content=contents)),
        approval=published.approval,
        bundle_id=published.id,
        version=published.version,
        now=published.published_at,
    )
    issues = validate_bundle(bundle=detached).issues
    assert any(issue.code == "candidate_hash" for issue in issues)
    assert any(issue.code == "unresolved_shape_reference" for issue in issues)
    with pytest.raises(InvalidBundleError):
        _ = detached.serialize()
    raw = _json(payload=published.serialize())
    approval = raw["approval"]
    assert isinstance(approval, dict)
    approval["candidate_id"] = "altered"
    with pytest.raises(InvalidBundleError) as failure:
        _ = DomainModelBundle.deserialize(payload=json.dumps(raw))
    assert failure.value.issues[0].code == "bundle_shape"
