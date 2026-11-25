"""Read a selected local catalog and reject substituted or escaping assets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Client,
    ClientConfiguration,
    InvalidReferencePackError,
    ReferencePackNotFoundError,
    SourceReadError,
)
from domain_kernel.configuration import FilesystemReader, ReferencePackCatalog
from domain_kernel.shared.hashing import hash_bytes
from tests.support.reference_packs.write_catalog import write_catalog

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_catalog_selects_only_configured_exact_bytes(tmp_path: Path) -> None:
    pack = write_catalog(root=tmp_path / "packs")
    reader = FilesystemReader(name="approved", root="packs")
    settings = ClientConfiguration(
        base_dir=tmp_path,
        readers=[reader],
        reference_packs=ReferencePackCatalog(reader=reader),
    )
    client = Client(config=settings)
    assert (await client.list_reference_packs()).items == (pack,)
    assert await client.get_reference_pack(key=pack.pin.key, version=pack.pin.version) == pack
    with pytest.raises(ReferencePackNotFoundError):
        _ = await client.get_reference_pack(key=pack.pin.key, version="unlisted")
    no_catalog = Client(config=ClientConfiguration(base_dir=tmp_path))
    assert not (await no_catalog.list_reference_packs()).items
    with pytest.raises(ReferencePackNotFoundError):
        _ = await no_catalog.get_reference_pack(key=pack.pin.key, version=pack.pin.version)
    _ = (tmp_path / "packs" / "systems.json").write_bytes(b"changed bytes")
    with pytest.raises(InvalidReferencePackError) as error:
        _ = await client.get_reference_pack(key=pack.pin.key, version=pack.pin.version)
    assert error.value.issues[0].code == "transport_hash"


async def test_catalog_reader_refuses_a_symlinked_asset(tmp_path: Path) -> None:
    pack = write_catalog(root=tmp_path / "packs")
    target = tmp_path / "outside.json"
    _ = target.write_bytes(pack.serialize())
    asset = tmp_path / "packs" / "systems.json"
    asset.unlink()
    asset.symlink_to(target)
    reader = FilesystemReader(name="approved", root="packs")
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=[reader],
            reference_packs=ReferencePackCatalog(reader=reader),
        )
    )
    with pytest.raises(SourceReadError):
        _ = await client.get_reference_pack(key=pack.pin.key, version=pack.pin.version)


async def test_catalog_rejects_duplicate_pins_for_one_release(tmp_path: Path) -> None:
    pack = write_catalog(root=tmp_path / "packs")
    manifest = tmp_path / "packs" / "catalog.json"
    payload = pack.serialize()
    keys = {
        "key": pack.pin.key,
        "version": pack.pin.version,
        "path": "systems.json",
        "payload_hash": hash_bytes(content=payload).value,
    }
    _ = manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "packs": [
                    {**keys, "content_hash": pack.pin.content_hash.value},
                    {**keys, "content_hash": hash_bytes(content=b"different pack").value},
                ],
            }
        )
    )
    reader = FilesystemReader(name="approved", root="packs")
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            readers=[reader],
            reference_packs=ReferencePackCatalog(reader=reader),
        )
    )
    with pytest.raises(InvalidReferencePackError) as error:
        _ = await client.list_reference_packs()
    assert error.value.issues[0].code == "duplicate_catalog_version"
