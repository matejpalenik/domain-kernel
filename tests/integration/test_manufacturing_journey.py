"""Verify the packaged maintenance journey with its separately provisioned originals."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

from domain_kernel import Count, DomainModelBundle
from examples.manufacturing_quickstart import run_manufacturing, write_manufacturing_delivery

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_wrong_manufacturing_original_stops_before_workspace_setup(tmp_path: Path) -> None:
    originals = tmp_path / "originals"
    originals.mkdir()
    _ = (originals / "atlas-copco-lfx-2-0.pdf").write_bytes(b"%PDF-1.7\nwrong edition")
    workspace = tmp_path / "state"
    with pytest.raises(ValueError, match="matching the acquisition manifest"):
        _ = await run_manufacturing(originals=originals, workspace=workspace)
    assert not workspace.exists()


async def test_independent_consumers_read_reviewed_manufacturing_releases(tmp_path: Path) -> None:
    if not (originals := os.environ.get("DK_TEST_MANUFACTURING_ORIGINALS")):
        pytest.skip("Provision the two pinned manufacturing originals")
    delivered = await run_manufacturing(
        originals=Path(originals),
        workspace=tmp_path / "producer",
    )
    first = DomainModelBundle.deserialize(payload=delivered.first.serialize())
    reviewed = DomainModelBundle.deserialize(payload=delivered.current.serialize())
    assert (first.version, reviewed.version) == ("1.0.0", "1.1.0")
    machine = reviewed.get_concept(name="machine")
    assert machine.id == first.get_concept(name=machine.name).id
    assert first.get_concept(name=machine.name).get_attribute(
        name="pressure-readings"
    ).max_items == Count(value=4)
    assert machine.get_attribute(name="pressure-readings").max_items == Count(value=5)
    assert machine.get_attribute(name="asset-code").required
    assert machine.get_key(name="site-asset-identity").attributes == (
        machine.get_attribute(name="site").id,
        machine.get_attribute(name="asset-code").id,
    )
    model_type = reviewed.get_concept(name="machine-type")
    assert model_type.id != machine.id
    assert model_type.evidence
    assert all(item.source.byte_length for item in model_type.evidence)
    assert delivered.exact_history
    assert delivered.semantic.publication.candidate.baseline == reviewed.model_version
    output = tmp_path / "delivery"
    write_manufacturing_delivery(result=delivered, output=output)
    shutil.rmtree(tmp_path / "producer")
    consumers = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "examples.embedding_acceptance",
        "--delivery",
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(consumers.communicate(), timeout=30)
    finally:
        if consumers.returncode is None:
            consumers.kill()
            _ = await consumers.wait()
    assert consumers.returncode == 0, stderr.decode()
    assert stdout.decode().splitlines() == [
        "FDE reviewed local maintenance-record from release 1.1.0",
        "ERP validated Press-17 and retained the site/asset-code key obligation",
        "GraphRAG validated host facts against the exact ontology and instance shapes",
    ]
