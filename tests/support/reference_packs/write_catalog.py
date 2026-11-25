"""Write a deterministic reference-pack catalog for integration tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from domain_kernel import (
    ConceptDefinition,
    ObligationId,
    ObligationKind,
    Pattern,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackObligation,
    ReferencePackSpec,
)
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from pathlib import Path


def write_catalog(
    *, root: Path, with_coverage: bool = False, version: str = "1.0.0"
) -> ReferencePack:
    """Write one exact pack and its manifest, and return the published pack."""
    definition = ReferenceDefinition(
        id=ReferenceDefinitionId(value="system"),
        name="system",
        meaning="An application system.",
        provenance="Authored fixture.",
        body=ConceptDefinition(),
    )
    required = ReferencePackObligation(
        id=ObligationId(value="system-coverage"),
        description="Cover the reference system.",
        kind=ObligationKind.COVERAGE,
        required=True,
        reference_ids=[definition.id],
        validator_id="domain-kernel.coverage@1.0",
    )
    draft = ReferencePack.compose(
        spec=ReferencePackSpec(
            key="example.catalog",
            version=version,
            title="Application catalog",
            applicability="Reference vocabulary",
            provenance="Authored fixture",
            license="Apache-2.0",
            definitions=[definition],
            obligations=[required] if with_coverage else [],
            patterns=[
                Pattern(
                    name="system",
                    description="Reuse a system.",
                    definitions=[definition],
                    entrypoint_ids=[definition.id],
                )
            ],
        ),
        actor="author",
        reason="Compose a portable fixture.",
    )
    assert draft.pack is not None
    pack = draft.pack
    payload = pack.serialize()
    root.mkdir()
    _ = (root / "systems.json").write_bytes(payload)
    _ = (root / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "packs": [
                    {
                        "key": pack.pin.key,
                        "version": pack.pin.version,
                        "path": "systems.json",
                        "content_hash": pack.pin.content_hash.value,
                        "payload_hash": hash_bytes(content=payload).value,
                    }
                ],
            }
        )
    )
    return pack
