"""Resolve exact packs and dependencies from explicitly configured portable files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, final

from domain_kernel.modeling.domain.bundle_shapes import parse_wire_record
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.modeling.domain.portable_json import PortableReadError, read_portable_object
from domain_kernel.reference_packs.api.packs import ReferencePack
from domain_kernel.reference_packs.domain.contracts import ReferenceAssetKind
from domain_kernel.shared.contracts import Issue, Page
from domain_kernel.shared.errors import (
    DomainKernelError,
    InvalidReferencePackError,
    ReferencePackNotFoundError,
    ResourceLimitError,
    SourceNotFoundError,
    StaleStateError,
)
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.sources.infrastructure.filesystem_reader import FilesystemSourceReader

_MAX_DEPENDENCY_DEPTH = 16
type _Version = tuple[str, str]


@dataclass(frozen=True, kw_only=True)
class _Entry:
    key: str
    version: str
    path: str
    content_hash: ContentHash
    payload_hash: ContentHash

    def __post_init__(self) -> None:
        TextValidation.require_text(value=self.path, field="Catalog path")
        RuntimeTypeValidation.require_exact(
            value=self.payload_hash, expected=ContentHash, field="Catalog transport hash"
        )
        _ = self.pin

    @property
    def selection(self) -> _Version:
        return self.key, self.version

    @property
    def pin(self) -> ReferencePackPin:
        return ReferencePackPin(key=self.key, version=self.version, content_hash=self.content_hash)


@dataclass(frozen=True, kw_only=True)
class _Manifest:
    schema_version: Literal[1]
    packs: Sequence[_Entry]


def _invalid(*, code: str, message: str) -> InvalidReferencePackError:
    return InvalidReferencePackError(issues=(Issue(code=code, path=("catalog",), message=message),))


def _page_start(*, cursor: PageCursor | None, fingerprint: str) -> int:
    if cursor is None:
        return 0
    RuntimeTypeValidation.require_exact(value=cursor, expected=PageCursor, field="Catalog cursor")
    token, _, index = cursor.value.rpartition("/")
    if token != fingerprint:
        raise StaleStateError(
            message="Start a new listing of the configured reference-pack catalog."
        )
    try:
        offset = int(index)
    except ValueError:
        raise ValueError("Use the cursor from this catalog listing") from None
    if offset < 1:
        raise ValueError("Use the cursor from this catalog listing")
    return offset


@final
class Catalog:
    """Read an exact set of approved versions through a bounded file binding."""

    def __init__(
        self,
        *,
        reader: FilesystemSourceReader,
        max_bytes: int,
        max_entries: int,
    ) -> None:
        """Bind transport and configured limits without accessing the reader."""
        self._reader = reader
        self._max_bytes = max_bytes
        self._max_entries = max_entries

    async def get(self, *, key: str, version: str) -> ReferencePack:
        """Read an explicitly listed version and verify its exact dependency closure."""
        entries, _ = await self._manifest()
        selected = entries.get((key, version))
        if selected is None:
            raise ReferencePackNotFoundError
        return await self._load(entry=selected, entries=entries, verified={}, ancestry=())

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ReferencePack]:
        """Read catalog definitions in key/version order with a manifest-bound cursor."""
        entries, fingerprint = await self._manifest()
        start = _page_start(cursor=cursor, fingerprint=fingerprint)
        names = sorted(entries)
        selected = names[start : start + limit]
        verified: dict[_Version, ReferencePack] = {}
        items = tuple(
            [
                await self._load(
                    entry=entries[name], entries=entries, verified=verified, ancestry=()
                )
                for name in selected
            ]
        )
        end = start + len(selected)
        next_cursor = PageCursor(value=f"{fingerprint}/{end}") if end < len(names) else None
        return Page(items=items, next_cursor=next_cursor)

    async def _manifest(self) -> tuple[dict[_Version, _Entry], str]:
        try:
            payload = await self._reader.read(
                relative_path="catalog.json", max_bytes=self._max_bytes
            )
        except SourceNotFoundError:
            raise ReferencePackNotFoundError from None
        try:
            raw = read_portable_object(
                payload=payload,
                expected_hash=None,
                max_bytes=self._max_bytes,
                resource="catalog",
            )
            manifest = parse_wire_record(document=raw, record=_Manifest)
        except PortableReadError as error:
            raise InvalidReferencePackError(issues=(error.issue,)) from None
        except (ValueError, TypeError, DomainKernelError):
            raise _invalid(
                code="catalog_format",
                message="Check the approved versioned reference-pack manifest.",
            ) from None
        if len(manifest.packs) > self._max_entries:
            raise ResourceLimitError
        entries = {entry.selection: entry for entry in manifest.packs}
        if len(entries) != len(manifest.packs):
            raise _invalid(
                code="duplicate_catalog_version",
                message="List each exact pack key and version once.",
            )
        return entries, hash_bytes(content=payload).value

    async def _load(
        self,
        *,
        entry: _Entry,
        entries: dict[_Version, _Entry],
        verified: dict[_Version, ReferencePack],
        ancestry: tuple[_Version, ...],
    ) -> ReferencePack:
        if (stored := verified.get(entry.selection)) is not None:
            return stored
        if entry.selection in ancestry or len(ancestry) >= _MAX_DEPENDENCY_DEPTH:
            raise _invalid(
                code="catalog_dependency_cycle",
                message="Supply a bounded acyclic pack dependency graph.",
            )
        try:
            payload = await self._reader.read(relative_path=entry.path, max_bytes=self._max_bytes)
        except SourceNotFoundError:
            raise _invalid(
                code="catalog_asset_missing",
                message="Restore the file for this catalog entry.",
            ) from None
        pack = ReferencePack.deserialize(
            payload=payload,
            expected_hash=entry.payload_hash,
            max_bytes=self._max_bytes,
        )
        if pack.pin != entry.pin:
            raise _invalid(
                code="catalog_pack_pin",
                message="Restore the exact pack selected in the manifest.",
            )
        for dependency in pack.dependencies:
            if dependency.kind is not ReferenceAssetKind.REFERENCE_PACK:
                continue
            found = entries.get((dependency.key, dependency.version))
            if found is None or found.content_hash != dependency.content_hash:
                raise _invalid(
                    code="catalog_dependency_pin",
                    message="Supply the exact listed upstream pack.",
                )
            _ = await self._load(
                entry=found,
                entries=entries,
                verified=verified,
                ancestry=(*ancestry, entry.selection),
            )
        verified[entry.selection] = pack
        return pack
