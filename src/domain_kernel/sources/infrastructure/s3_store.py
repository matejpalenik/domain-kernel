"""Persist immutable artifacts and originals in a configured S3 destination."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, final, override

from domain_kernel._shared.application.artifacts import ArtifactStore, ArtifactWrite
from domain_kernel._shared.domain.artifact_conflict_error import ArtifactConflictError
from domain_kernel._shared.domain.audit import Artifact
from domain_kernel._shared.domain.paths import relative_parts
from domain_kernel._shared.domain.record_encoding import record_bytes
from domain_kernel.shared.errors import ResourceLimitError, SourceReadError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.sources.application.ports import OriginalStore, ReadableOriginalStore
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.infrastructure.aws import (
    S3Connection,
    S3RequestError,
    run_s3_request,
    s3_request,
)
from domain_kernel.sources.infrastructure.s3_reader import object_version, read_s3_body, s3_prefix

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import GetObjectRequestTypeDef

    from domain_kernel.configuration import S3Store
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.sources.domain.models import SourceRevision
    from domain_kernel.sources.infrastructure.aws import AwsCredentialProvider


_DEFAULT_MAX_BYTES = 64 * 1024 * 1024
_REQUEST_HASH = "dk-request-hash"
_ORIGINAL_HASH = "dk-original-hash"
_BINARY = "application/octet-stream"


def _scoped_key(*, project_id: ProjectId, key: str, root: str) -> str:
    parts = relative_parts(path=key)
    scope = (root, project_id.value)
    if (
        parts[: len(scope)] != scope
        or len(parts) <= len(scope)
        or "/".join(parts) != key
        or any(":" in part for part in parts)
    ):
        raise SourceReadError(message="Use a canonical object key under the owning project.")
    return key


def _read_request(*, bucket: str, key: str, version: str | None) -> GetObjectRequestTypeDef:
    if version is None:
        return {"Bucket": bucket, "Key": key}
    kind, _, identity = version.partition(":")
    if identity and kind == "version":
        return {"Bucket": bucket, "Key": key, "VersionId": identity}
    if identity and kind == "etag":
        return {"Bucket": bucket, "Key": key, "IfMatch": identity}
    raise ArtifactConflictError


@dataclass(frozen=True, kw_only=True)
class _Object:
    data: bytes
    version: str
    metadata: Mapping[str, str]
    media_type: str


@dataclass(frozen=True, kw_only=True)
class _Write:
    key: str
    data: bytes
    digest: ContentHash
    media_type: str
    metadata: dict[str, str]


@final
class _Destination:
    def __init__(
        self, *, config: S3Store, credentials: AwsCredentialProvider | None, client: S3Client | None
    ) -> None:
        self.name = config.name
        self._prefix = s3_prefix(prefix=config.prefix)
        self._bucket = config.bucket
        self._connection = S3Connection(config=config, credentials=credentials, client=client)
        self.scope = hash_json(
            value=("s3-store", self.name, config.bucket, self._prefix, config.region)
        ).value

    def get(self, *, key: str, limit: int, version: str | None = None) -> _Object | None:
        request = _read_request(bucket=self._bucket, key=self._prefix + key, version=version)
        with self._connection.open() as client:
            try:
                response = s3_request(call=lambda: client.get_object(**request))
            except S3RequestError as error:
                if error.status == HTTPStatus.NOT_FOUND:
                    return None
                if error.status == HTTPStatus.PRECONDITION_FAILED:
                    raise ArtifactConflictError from None
                raise
            data = s3_request(call=lambda: read_s3_body(response=response, limit=limit))
        actual = object_version(version=response.get("VersionId"), etag=response.get("ETag"))
        if version is not None and version != actual:
            raise ArtifactConflictError
        return _Object(
            data=data,
            version=actual,
            metadata=response.get("Metadata", {}),
            media_type=response.get("ContentType", ""),
        )

    def put(self, *, write: _Write) -> str:
        checksum = b64encode(bytes.fromhex(write.digest.value.removeprefix("sha256:"))).decode()
        for _ in range(2):
            try:
                with self._connection.open() as client:
                    response = s3_request(
                        call=lambda: client.put_object(
                            Bucket=self._bucket,
                            Key=self._prefix + write.key,
                            Body=write.data,
                            ContentLength=len(write.data),
                            ContentType=write.media_type,
                            Metadata=write.metadata,
                            ChecksumSHA256=checksum,
                            IfNoneMatch="*",
                        )
                    )
                return object_version(version=response.get("VersionId"), etag=response.get("ETag"))
            except S3RequestError as error:
                if error.status not in (HTTPStatus.PRECONDITION_FAILED, HTTPStatus.CONFLICT):
                    raise
                try:
                    existing = self.get(key=write.key, limit=len(write.data))
                except ResourceLimitError:
                    raise ArtifactConflictError from None
                if existing is not None:
                    if (
                        existing.metadata != write.metadata
                        or existing.media_type != write.media_type
                        or hash_bytes(content=existing.data) != write.digest
                    ):
                        raise ArtifactConflictError from None
                    return existing.version
                if error.status == HTTPStatus.PRECONDITION_FAILED:
                    break
        raise SourceReadError(message="Retry the same conditional S3 write intent.", retryable=True)


def _payload(*, chunks: Iterable[bytes]) -> bytes:
    buffer = bytearray()
    for chunk in chunks:
        if type(chunk) is not bytes:
            raise TypeError("Send artifact content as byte chunks.")
        if len(buffer) + len(chunk) > _DEFAULT_MAX_BYTES:
            raise ResourceLimitError(message="Use an artifact within the S3 write budget.")
        buffer.extend(chunk)
    return bytes(buffer)


def _request_hash(*, request: ArtifactWrite) -> str:
    return hash_bytes(content=record_bytes(value=request, root_type=ArtifactWrite)).value


@final
class S3ArtifactStore(ArtifactStore):
    """Create artifacts once with exact byte and request metadata verification."""

    def __init__(
        self,
        *,
        config: S3Store,
        credentials: AwsCredentialProvider | None = None,
        client: S3Client | None = None,
    ) -> None:
        """Bind an independently configured output provider without contacting S3."""
        self._destination = _Destination(config=config, credentials=credentials, client=client)
        self.provider_scope = self._destination.scope

    def _key(self, *, artifact: Artifact) -> str:
        if artifact.store != self._destination.name:
            raise ArtifactConflictError
        return _scoped_key(project_id=artifact.project_id, key=artifact.key, root="projects")

    @override
    def put(self, *, request: ArtifactWrite, chunks: Iterable[bytes]) -> Artifact:
        """Conditionally create an exact artifact or recover the same immutable write."""
        key = self._key(artifact=request.artifact())
        data = _payload(chunks=chunks)
        if hash_bytes(content=data) != request.expected_hash:
            raise ArtifactConflictError
        version = self._destination.put(
            write=_Write(
                key=key,
                data=data,
                digest=request.expected_hash,
                media_type=request.media_type,
                metadata={_REQUEST_HASH: _request_hash(request=request)},
            )
        )
        return request.artifact(provider_version=version)

    def _exact(self, *, artifact: Artifact, limit: int) -> bytes | None:
        key = self._key(artifact=artifact)
        if artifact.provider_version is None:
            raise ArtifactConflictError
        stored = self._destination.get(key=key, limit=limit, version=artifact.provider_version)
        if stored is None:
            return None
        if not stored.media_type or hash_bytes(content=stored.data) != artifact.content_hash:
            raise ArtifactConflictError
        request = ArtifactWrite(
            project_id=artifact.project_id,
            model_id=artifact.model_id,
            store=artifact.store,
            key=artifact.key,
            media_type=stored.media_type,
            expected_hash=artifact.content_hash,
            projection_limits=artifact.projection_limits,
            semantic=artifact.semantic,
            schema=artifact.schema,
            consumer_obligations=artifact.consumer_obligations,
        )
        if stored.metadata != {_REQUEST_HASH: _request_hash(request=request)}:
            raise ArtifactConflictError
        return stored.data

    @override
    def get(self, *, artifact: Artifact, max_bytes: int) -> bytes:
        """Retrieve the exact stored artifact and recheck its metadata and byte hash."""
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Set a positive artifact read limit.")
        data = self._exact(artifact=artifact, limit=min(max_bytes, _DEFAULT_MAX_BYTES))
        if data is None:
            raise SourceReadError(message="Open the exact artifact in the configured S3 store.")
        return data

    @override
    def verify(self, *, artifact: Artifact) -> bool:
        """Report whether this exact destination object can be recovered."""
        try:
            return self._exact(artifact=artifact, limit=_DEFAULT_MAX_BYTES) is not None
        except (ArtifactConflictError, ResourceLimitError):
            return False


@final
class S3OriginalStore(OriginalStore, ReadableOriginalStore):
    """Archive exact originals under a configured content-addressed S3 prefix."""

    def __init__(
        self,
        *,
        config: S3Store,
        credentials: AwsCredentialProvider | None = None,
        client: S3Client | None = None,
    ) -> None:
        """Bind independently configured original storage."""
        self._destination = _Destination(config=config, credentials=credentials, client=client)

    @property
    @override
    def provider_scope(self) -> str:
        """Return the configured destination's noncredential identity."""
        return self._destination.scope

    async def _exact(
        self, *, key: str, project_id: ProjectId, digest: ContentHash, size: int, limit: int
    ) -> _Object | None:
        path = _scoped_key(project_id=project_id, key=key, root="sources")
        captured = await run_s3_request(call=lambda: self._destination.get(key=path, limit=limit))
        if captured is not None and (
            len(captured.data) != size
            or hash_bytes(content=captured.data) != digest
            or captured.metadata != {_ORIGINAL_HASH: digest.value}
        ):
            raise SourceRevisionMismatchError
        return captured

    @override
    async def verify(
        self, *, project_id: ProjectId, key: str, digest: ContentHash, byte_length: int
    ) -> Artifact | None:
        """Read and verify immutable bytes for the same original-copy intent."""
        stored = await self._exact(
            key=key,
            project_id=project_id,
            digest=digest,
            size=byte_length,
            limit=min(byte_length, _DEFAULT_MAX_BYTES),
        )
        if stored is None:
            return None
        return Artifact(
            project_id=project_id,
            store=self._destination.name,
            key=key,
            content_hash=digest,
            provider_version=stored.version,
        )

    @override
    async def put(
        self, *, project_id: ProjectId, key: str, content: bytes, digest: ContentHash
    ) -> Artifact:
        """Conditionally archive exactly the bytes captured by source ingestion."""
        path = _scoped_key(project_id=project_id, key=key, root="sources")
        if len(content) > _DEFAULT_MAX_BYTES:
            raise ResourceLimitError(message="Use an original within the S3 write budget.")
        if hash_bytes(content=content) != digest:
            raise SourceRevisionMismatchError
        write = _Write(
            key=path,
            data=content,
            digest=digest,
            media_type=_BINARY,
            metadata={_ORIGINAL_HASH: digest.value},
        )
        version = await run_s3_request(call=lambda: self._destination.put(write=write))
        return Artifact(
            project_id=project_id,
            store=self._destination.name,
            key=key,
            content_hash=digest,
            provider_version=version,
        )

    @override
    async def read_original(
        self, *, key: str, revision: SourceRevision, max_bytes: int
    ) -> bytes | None:
        """Reopen a bounded archived original and verify its exact source revision."""
        stored = await self._exact(
            key=key,
            project_id=revision.project_id,
            digest=ContentHash(value=revision.revision_id.value),
            size=revision.byte_length,
            limit=min(max_bytes, _DEFAULT_MAX_BYTES),
        )
        return None if stored is None else stored.data
