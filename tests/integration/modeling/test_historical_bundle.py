"""Keep a published bundle independent of the SDK version that wrote it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    ActivityId,
    AttributeId,
    BundleId,
    ConditionId,
    ContentHash,
    Count,
    DefinitionId,
    DomainModelBundle,
    FlowId,
    GatewayId,
)

if TYPE_CHECKING:
    from typing import Final

pytestmark = pytest.mark.integration

_HASH: Final = ContentHash(
    value="sha256:59dfc48b4c3ae2d5d98c2ded66a03c702c5346c4a745fd82bc5664c048f95ac1"
)


def test_historical_bundle_keeps_exact_bytes_and_consumer_identities(tmp_path: Path) -> None:
    # Captured from publish() by test_portable_bundle.py's writer at 325d3a9.
    fixture = Path(__file__).parent / "fixtures" / "published_v1.json"
    payload = fixture.read_bytes().removesuffix(b"\n")
    bundle = DomainModelBundle.deserialize(payload=payload, expected_hash=_HASH)
    actor = bundle.get_concept(name="actor")
    identifier = actor.get_attribute(name="identifier")

    assert bundle.id == BundleId(value="b1205e443e674e50bf71bcf5cc474108")
    assert bundle.version == "1.0.0"
    assert bundle.approval.actor == "publisher"
    assert actor.id == DefinitionId(value="251cd8d444c2485e80a12864373056a0")
    assert identifier.id == AttributeId(value="88d5559628814619b172e335658e22af")
    assert actor.get_key(name="identity").attributes == (identifier.id,)
    assert actor.get_attribute(name="contacts").max_items == Count(value=3)
    assert bundle.serialize() == payload

    consumer = """
from domain_kernel import DomainModelBundle
import sys

bundle = DomainModelBundle.deserialize(payload=sys.stdin.buffer.read())
print(bundle.version, bundle.get_concept(name="actor").get_key(name="identity").name)
"""
    result = subprocess.run(  # noqa: S603 -- Fixed SDK-only consumer in a fresh directory.
        [sys.executable, "-I", "-c", consumer],
        cwd=tmp_path,
        input=payload,
        capture_output=True,
        timeout=15,
        check=True,
    )
    assert result.stdout == b"1.0.0 identity\n"


def test_pre_refactor_process_bundle_preserves_parts_and_typed_edges() -> None:
    # Captured from publish() in test_descriptive_processes.py at 34ab710.
    fixture = Path(__file__).parent / "fixtures" / "published_descriptive_process.json"
    payload = fixture.read_bytes().removesuffix(b"\n")
    bundle = DomainModelBundle.deserialize(
        payload=payload,
        expected_hash=ContentHash(
            value="sha256:687fd6c0f18fe876f701463b700d7a39c1b05491c6093e95bcd9f9fc71c7c15a"
        ),
    )
    process = bundle.get_process(process_id=DefinitionId(value="3c456ed055c3438c91d5c6a94de7b7ef"))
    activity = process.get_activity(
        activity_id=ActivityId(value="89582b1e89fd4afbb846d522b6dbace0")
    )
    flow = process.get_flow(flow_id=FlowId(value="fd306c7d63044d75aa3c4a873a17faf7"))
    assert flow.source_id == GatewayId(value="cb1376aa7d014fc28e49ea4236983d64")
    assert flow.target_id == activity.id
    assert flow.condition_id == ConditionId(value="1afaef287d42468bb67fa568f08890e9")
    assert activity.decision_id == DefinitionId(value="667b6c891ce4406bb4037c38fe8fd77d")
    assert process.get_condition(name="significant").id == flow.condition_id
    assert bundle.serialize() == payload
