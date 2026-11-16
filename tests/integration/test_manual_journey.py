"""Exercise the runnable recruitment recipe through two releases and a standalone consumer."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from domain_kernel import CollectionKind, Count, ModelKind

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_recruitment_quickstart_reloads_two_reviewed_versions(tmp_path: Path) -> None:
    from examples.recruitment_quickstart import author_releases, read_release  # noqa: PLC0415

    first, second = await author_releases(workspace=tmp_path)
    received_first = read_release(payload=first.serialize())
    received_second = read_release(payload=second.serialize())
    assert received_first == first
    assert received_second == second
    assert received_first.kind is ModelKind.OBSERVED
    assert (received_first.version, received_second.version) == ("1.0.0", "1.1.0")
    original = received_first.get_concept(name="recruitment-ai-system")
    refined = received_second.get_concept(concept_id=original.id)
    original_purpose = original.get_attribute(name="intended-purpose")
    refined_purpose = refined.get_attribute(attribute_id=original_purpose.id)
    assert original_purpose.collection is refined_purpose.collection is CollectionKind.SET
    assert original_purpose.min_items == refined_purpose.min_items == Count(value=0)
    assert original_purpose.max_items == Count(value=2)
    assert refined_purpose.max_items == Count(value=3)
    assert original.get_key(name="system-identity") == refined.get_key(name="system-identity")
    assert received_second.publication.changes.before == first.model_version
    assert any(
        item.actor == "demo:reviewer" and item.applied_changes.changes
        for item in received_second.publication.candidate.decisions
    )


async def test_recipe_cli_transfers_both_versions_to_an_independent_process() -> None:
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "examples.recruitment_quickstart"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert "Received version: 1.0.0" in result.stdout
    assert "Received version: 1.1.0" in result.stdout
    assert "Purpose maximum: 2" in result.stdout
    assert "Purpose maximum: 3" in result.stdout
