"""Provision immutable catalog files in an explicitly owned example directory."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import ReferencePack
    from domain_kernel.shared.json_value import JsonValue


def provision_example_catalog(*, root: Path, packs: Sequence[ReferencePack]) -> None:
    """Publish the initial manifest and exact local files for the example reader."""
    if (root / "catalog.json").is_file():
        return
    root.mkdir(parents=True, exist_ok=True)
    entries: list[JsonValue] = []
    with TemporaryDirectory(prefix="catalog-stage-", dir=root) as staging:
        stage = Path(staging)
        for pack in packs:
            payload = pack.serialize()
            transport = Hashing.hash_bytes(content=payload)
            name = f"{transport.value.removeprefix('sha256:')}.json"
            _ = (stage / name).write_bytes(payload)
            try:
                (root / name).hardlink_to(stage / name)
            except FileExistsError:
                if (root / name).read_bytes() != payload:
                    raise ValueError("Restore the exact immutable catalog file") from None
            entries.append(
                {
                    "key": pack.pin.key,
                    "version": pack.pin.version,
                    "path": name,
                    "content_hash": pack.pin.content_hash.value,
                    "payload_hash": transport.value,
                }
            )
        manifest = CanonicalJson.encode(value={"schema_version": 1, "packs": entries})
        selected = stage / "catalog.json"
        _ = selected.write_bytes(manifest)
        try:
            (root / selected.name).hardlink_to(selected)
        except FileExistsError:
            # Another execution may already have provisioned this named sample catalog.
            return
