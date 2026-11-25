"""Acquire verified exact revisions under an explicit S3 bucket and prefix."""

from __future__ import annotations

from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING, final, override

from domain_kernel.shared.contracts import Page
from domain_kernel.shared.domain.paths import relative_parts
from domain_kernel.shared.errors import ResourceLimitError, SourceReadError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.sources.application.contracts import ReaderLocation, SourceEntry, SourceEntryKind
from domain_kernel.sources.application.ports import AcquiredSource, SourceBuffer, SourceReader
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.models import FileOrigin
from domain_kernel.sources.infrastructure.aws import (
    S3Connection,
    S3RequestError,
    run_s3_request,
    s3_request,
)
from domain_kernel.sources.infrastructure.remote_listing import (
    listing_binding,
    next_page,
    read_continuation,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import (
        GetObjectOutputTypeDef,
        GetObjectRequestTypeDef,
        HeadObjectRequestTypeDef,
        ListObjectsV2RequestTypeDef,
    )

    from domain_kernel.configuration import S3Reader, SourceSelectionLimits
    from domain_kernel.shared.identifiers.page_cursor import PageCursor
    from domain_kernel.sources.domain.models import ProcessingLimits, SourceRevision
    from domain_kernel.sources.infrastructure.aws import AwsCredentialProvider


def s3_prefix(*, prefix: str) -> str:
    """Return the full configured prefix with its delimiter."""
    return "" if not prefix else "/".join(relative_parts(path=prefix.rstrip("/"))) + "/"


def read_s3_body(*, response: GetObjectOutputTypeDef, limit: int) -> bytes:
    """Read at most the configured budget and close the provider stream."""
    with closing(response["Body"]) as stream:
        length = response.get("ContentLength", -1)
        if length > limit:
            raise ResourceLimitError(message="Select an S3 object within the byte limit.")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ResourceLimitError(message="Select an S3 object within the byte limit.")
    if len(data) != length:
        raise SourceReadError(message="Retry an incomplete S3 object read.", retryable=True)
    return data


def object_version(*, version: str | None, etag: str | None) -> str:
    """Use the immutable version ID when available and retain an opaque ETag guard otherwise."""
    if version and version != "null":
        return "version:" + version
    if etag:
        return "etag:" + etag
    raise SourceReadError(message="S3 did not return a usable object revision guard.")


@final
class S3ReaderAdapter(SourceReader):
    """Read and enumerate approved S3 objects with exact revision and byte guards."""

    def __init__(
        self,
        *,
        config: S3Reader,
        credentials: AwsCredentialProvider | None = None,
        client: S3Client | None = None,
    ) -> None:
        """Bind an approved prefix and optional caller-owned AWS client."""
        self._config = config
        self._prefix = s3_prefix(prefix=config.prefix)
        self._connection = S3Connection(config=config, credentials=credentials, client=client)
        self._scope = hash_json(
            value=("s3", config.name, config.bucket, self._prefix, config.region)
        ).value

    @property
    @override
    def provider_scope(self) -> str:
        """Return the noncredential binding of this reader."""
        return self._scope

    def _relative(self, *, location: ReaderLocation, allow_root: bool = False) -> str:
        if location.reader != self._config.name:
            raise SourceReadError(message="Select a location in this configured S3 reader.")
        return "/".join(relative_parts(path=location.path, allow_root=allow_root))

    def _children(
        self, *, prefix: str, limit: int, binding: str, token: str | None
    ) -> Page[SourceEntry]:
        request: ListObjectsV2RequestTypeDef = {
            "Bucket": self._config.bucket,
            "Prefix": prefix,
            "Delimiter": "/",
            "MaxKeys": limit,
        }
        if token is not None:
            request["ContinuationToken"] = token
        with self._connection.open() as client:
            page = s3_request(call=lambda: client.list_objects_v2(**request))
        items: list[SourceEntry] = []
        for row in page.get("Contents", []):
            key = row.get("Key", "")
            if key != prefix:
                etag = row.get("ETag", "")
                items.append(
                    self._entry(
                        key=key,
                        prefix=prefix,
                        kind=SourceEntryKind.FILE,
                        version=object_version(version=None, etag=etag),
                    )
                )
        items.extend(
            self._entry(key=row.get("Prefix", ""), prefix=prefix, kind=SourceEntryKind.FOLDER)
            for row in page.get("CommonPrefixes", [])
        )
        if len(items) > limit or len({row.location.path for row in items}) != len(items):
            raise SourceReadError(message="S3 returned an invalid or overfull page of children.")
        following: str | None = page.get("NextContinuationToken", "")
        if page.get("IsTruncated", False):
            if not following or following == token:
                raise SourceReadError(message="S3 did not advance its listing continuation.")
        else:
            following = None
        return Page(items=items, next_cursor=next_page(token=following, binding=binding))

    def _entry(
        self, *, key: str, prefix: str, kind: SourceEntryKind, version: str | None = None
    ) -> SourceEntry:
        if not key.startswith(prefix):
            raise SourceReadError(message="S3 returned a child outside the selected prefix.")
        leaf = (
            key[len(prefix) :].removesuffix("/")
            if kind is SourceEntryKind.FOLDER
            else key[len(prefix) :]
        )
        if not leaf or "/" in leaf or leaf in (".", ".."):
            raise SourceReadError(
                message="S3 returned a non-immediate child of the selected prefix."
            )
        return SourceEntry(
            location=ReaderLocation(
                reader=self._config.name, path=key[len(self._prefix) :].rstrip("/")
            ),
            kind=kind,
            provider_scope=self._scope,
            provider_item_id=key,
            provider_version=version,
        )

    @override
    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]:
        """List and page only the immediate children under the configured prefix."""
        relative = self._relative(location=location, allow_root=True)
        prefix = self._prefix + (relative + "/" if relative else "")
        binding = listing_binding(scope=self._scope, location=location, limits=limits, limit=limit)
        token = read_continuation(cursor=cursor, binding=binding)
        return await run_s3_request(
            call=lambda: self._children(prefix=prefix, limit=limit, binding=binding, token=token)
        )

    def _fetch(
        self, *, key: str, limit: int, pin: str | None, expected_etag: str | None
    ) -> tuple[bytes, str]:
        version_id = (
            pin.removeprefix("version:") if pin is not None and pin.startswith("version:") else None
        )
        metadata_request: HeadObjectRequestTypeDef = {"Bucket": self._config.bucket, "Key": key}
        if version_id is not None:
            metadata_request["VersionId"] = version_id
        with self._connection.open() as client:
            head = s3_request(call=lambda: client.head_object(**metadata_request))
            etag = head.get("ETag", "")
            version = head.get("VersionId")
            actual = object_version(version=version, etag=etag)
            if (pin is not None and pin != actual) or (
                expected_etag is not None and expected_etag != "etag:" + (etag or "")
            ):
                raise SourceRevisionMismatchError
            if head.get("ContentLength", 0) > limit:
                raise ResourceLimitError(message="Select an S3 object within the byte limit.")
            request: GetObjectRequestTypeDef = {"Bucket": self._config.bucket, "Key": key}
            if version and version != "null":
                request["VersionId"] = version
            if etag:
                request["IfMatch"] = etag
            response = s3_request(call=lambda: client.get_object(**request))
            # Consume and close the bounded stream even on inconsistent provider metadata.
            data = s3_request(call=lambda: read_s3_body(response=response, limit=limit))
            if (
                response.get("ETag") != etag
                or object_version(version=response.get("VersionId"), etag=response.get("ETag"))
                != actual
            ):
                raise SourceRevisionMismatchError
        return data, actual

    @override
    @asynccontextmanager
    async def open(
        self,
        *,
        location: ReaderLocation,
        limits: ProcessingLimits,
        expected: SourceRevision | None = None,
        expected_entry: SourceEntry | None = None,
    ) -> AsyncGenerator[AcquiredSource]:
        """Open bounded bytes guarded by an explicitly inspected entry or revision."""
        relative = self._relative(location=location)
        key = self._prefix + relative
        pin = None
        if expected is not None:
            origin = expected.origin
            if (
                not isinstance(origin, FileOrigin)
                or (origin.reader, origin.provider_scope, origin.location)
                != (location.reader, self._scope, relative)
                or origin.provider_version is None
            ):
                raise SourceRevisionMismatchError
            pin = origin.provider_version
        entry_guard = None
        if expected_entry is not None:
            if (
                expected_entry.location != location
                or expected_entry.provider_scope != self._scope
                or expected_entry.provider_item_id != key
                or expected_entry.kind is not SourceEntryKind.FILE
                or expected_entry.provider_version is None
            ):
                raise SourceRevisionMismatchError
            entry_guard = expected_entry.provider_version
        try:
            data, version = await run_s3_request(
                call=lambda: self._fetch(
                    key=key, limit=limits.max_source_bytes, pin=pin, expected_etag=entry_guard
                )
            )
        except S3RequestError as error:
            if error.status in (404, 412) and (expected is not None or expected_entry is not None):
                raise SourceRevisionMismatchError from None
            raise
        digest = hash_bytes(content=data)
        if expected is not None and (
            digest.value != expected.revision_id.value or len(data) != expected.byte_length
        ):
            raise SourceRevisionMismatchError
        with BytesIO(data) as buffer:
            yield AcquiredSource(
                stream=SourceBuffer(data=buffer),
                origin=FileOrigin(
                    reader=location.reader,
                    provider_scope=self._scope,
                    location=relative,
                    provider_version=version,
                    acquired_at=datetime.now(tz=UTC),
                ),
                byte_length=len(data),
                content_hash=digest,
            )
