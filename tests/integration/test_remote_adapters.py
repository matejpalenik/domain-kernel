"""Verify actual provider requests without using account credentials."""

from __future__ import annotations

import asyncio
from importlib.util import find_spec
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from domain_kernel import (
    ProjectId,
    SourceId,
    SourceReadError,
    SourceRevision,
    SourceRevisionId,
    SourceRevisionMismatchError,
)
from domain_kernel.configuration import (
    AwsDefaultChain,
    EntraClientSecret,
    Env,
    S3Reader,
    SharePointReader,
    SourceSelectionLimits,
)
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.sources.application.contracts import ReaderLocation, SourceEntryKind
from domain_kernel.sources.domain.models import ProcessingLimits
from domain_kernel.sources.infrastructure.aws import AwsCredentialSnapshot, S3Connection

if TYPE_CHECKING:
    from collections.abc import Generator

    from httpx import Request, Response
    from mypy_boto3_s3 import S3Client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONTENT = b"Reviewed legal source bytes.\n"
_LIMITS = ProcessingLimits(
    max_source_bytes=256,
    max_concurrent_sources=1,
    max_expanded_bytes=512,
    max_pages=10,
)
_ETAG = '"opaque-etag"'
_S3_KEY = "manuals/ai-act.pdf"


class _AwsCredentials:
    def get_credentials(self) -> AwsCredentialSnapshot:
        return AwsCredentialSnapshot(
            access_key_id=SecretStr("stubbed"),
            secret_access_key=SecretStr("stubbed"),
        )


@pytest.fixture
def s3_config() -> S3Reader:
    return S3Reader(
        name="inputs",
        bucket="sources-test",
        prefix="manuals/",
        region="eu-central-1",
        credentials=AwsDefaultChain(),
    )


@pytest.fixture
def s3_api(*, s3_config: S3Reader) -> Generator[S3Client]:
    if find_spec("boto3") is None:
        pytest.skip("Install the s3 extra.")
    with S3Connection(
        config=s3_config, credentials=_AwsCredentials(), client=None
    ).open() as client:
        yield client


async def test_s3_pages_and_reads_the_inspected_version(
    *, s3_api: S3Client, s3_config: S3Reader
) -> None:
    from botocore.response import StreamingBody  # noqa: PLC0415 - Optional provider fixture.
    from botocore.stub import Stubber  # noqa: PLC0415 - Optional provider fixture.

    from domain_kernel import S3ReaderAdapter  # noqa: PLC0415 - Optional provider fixture.

    service = s3_api
    config = s3_config
    reader = S3ReaderAdapter(config=config, client=service)
    folder = ReaderLocation(reader="inputs", path=".")
    limits = SourceSelectionLimits()
    listing = {"Bucket": "sources-test", "Prefix": "manuals/", "Delimiter": "/", "MaxKeys": 1}
    target = {"Bucket": "sources-test", "Key": _S3_KEY}
    with Stubber(service) as stub:
        stub.add_response(
            "list_objects_v2",
            {
                "IsTruncated": True,
                "NextContinuationToken": "next",
                "Contents": [{"Key": _S3_KEY, "ETag": _ETAG, "Size": len(_CONTENT)}],
            },
            listing,
        )
        stub.add_response(
            "list_objects_v2",
            {"IsTruncated": False, "CommonPrefixes": [{"Prefix": "manuals/updates/"}]},
            {**listing, "ContinuationToken": "next"},
        )
        stub.add_response(
            "head_object",
            {"ETag": _ETAG, "VersionId": "first-version", "ContentLength": len(_CONTENT)},
            target,
        )
        stub.add_response(
            "get_object",
            {
                "ETag": _ETAG,
                "VersionId": "first-version",
                "ContentLength": len(_CONTENT),
                "Body": StreamingBody(BytesIO(_CONTENT), len(_CONTENT)),
            },
            {**target, "VersionId": "first-version", "IfMatch": _ETAG},
        )
        first = await reader.list_children(location=folder, limits=limits, limit=1)
        assert first.next_cursor is not None
        with pytest.raises(StaleStateError):
            _ = await reader.list_children(
                location=ReaderLocation(reader="inputs", path="other"),
                limits=limits,
                limit=1,
                cursor=first.next_cursor,
            )
        second = await reader.list_children(
            location=folder, limits=limits, limit=1, cursor=first.next_cursor
        )
        (file,) = first.items
        (child,) = second.items
        assert file.location.path == "ai-act.pdf"
        assert child.location.path == "updates"
        assert child.kind is SourceEntryKind.FOLDER
        assert second.next_cursor is None
        async with reader.open(
            location=file.location, limits=_LIMITS, expected_entry=file
        ) as acquired:
            assert acquired.stream.read() == _CONTENT
            assert acquired.content_hash == hash_bytes(content=_CONTENT)
            historical = SourceRevision(
                project_id=ProjectId(value="project"),
                source_id=SourceId(value="source"),
                revision_id=SourceRevisionId(value=acquired.content_hash.value),
                origin=acquired.origin,
                byte_length=acquired.byte_length,
            )
        stub.add_client_error(
            "head_object",
            service_error_code="NoSuchVersion",
            http_status_code=404,
            expected_params={**target, "VersionId": "first-version"},
        )
        with pytest.raises(SourceRevisionMismatchError):
            async with reader.open(location=file.location, limits=_LIMITS, expected=historical):
                pytest.fail("An expired revision must not fall back to the latest object.")
        stub.assert_no_pending_responses()


class _Token:
    def get_token(self, *, scope: str) -> SecretStr:
        assert scope == "https://graph.microsoft.com/.default"
        return SecretStr("graph-test-bearer")


@pytest.mark.parametrize("outside_host", [False, True])
async def test_graph_download_keeps_credentials_at_graph(*, outside_host: bool) -> None:
    if find_spec("httpx") is None:
        pytest.skip("Install the sharepoint extra.")
    import httpx  # noqa: PLC0415 - Optional provider fixture.

    from domain_kernel import SharePointReaderAdapter  # noqa: PLC0415 - Optional provider fixture.

    received: list[str] = []
    paths: list[str] = []
    updated = False

    def respond(request: Request) -> Response:
        received.append(request.url.host)
        if request.url.host == "publisher.sharepoint.com":
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=_CONTENT)
        assert request.headers["Authorization"] == "Bearer graph-test-bearer"
        resource = request.url.path
        paths.append(resource)
        if resource.endswith(("/items/record/content", "/items/record/versions/3.0/content")):
            host = "other.sharepoint.com" if outside_host else "publisher.sharepoint.com"
            return httpx.Response(
                302,
                headers={"Location": f"https://{host}/download?signature=test"},
            )
        if resource.endswith("/items/record/versions"):
            return httpx.Response(200, json={"value": [{"id": "4.0" if updated else "3.0"}]})
        assert resource.endswith("/items/approved:/ai-act.pdf")
        return httpx.Response(
            200,
            json={
                "id": "record",
                "name": "ai-act.pdf",
                "eTag": '"updated"' if updated else _ETAG,
                "size": len(_CONTENT),
                "file": {"mimeType": "application/pdf"},
                "webUrl": "https://publisher.sharepoint.com/sites/example/ai-act.pdf",
                "parentReference": {"driveId": "drive", "id": "approved"},
            },
        )

    config = SharePointReader(
        name="evidence",
        drive_id="drive",
        root_item_id="approved",
        credentials=EntraClientSecret(
            tenant_id="tenant", client_id="client", client_secret=Env(env="GRAPH_TEST_SECRET")
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer host-default"},
    ) as client:
        reader = SharePointReaderAdapter(config=config, credentials=_Token(), client=client)
        location = ReaderLocation(reader="evidence", path="ai-act.pdf")
        if outside_host:
            with pytest.raises(SourceReadError, match="outside the item's SharePoint host"):
                async with reader.open(location=location, limits=_LIMITS):
                    pytest.fail("Reject a cross-tenant redirect before opening bytes.")
        else:
            async with reader.open(location=location, limits=_LIMITS) as acquired:
                assert acquired.stream.read() == _CONTENT
                assert acquired.content_hash == hash_bytes(content=_CONTENT)
                pinned = SourceRevision(
                    project_id=ProjectId(value="project"),
                    source_id=SourceId(value="source"),
                    revision_id=SourceRevisionId(value=acquired.content_hash.value),
                    origin=acquired.origin,
                    byte_length=acquired.byte_length,
                )
            updated = True
            async with reader.open(
                location=location, limits=_LIMITS, expected=pinned
            ) as historical:
                assert historical.stream.read() == _CONTENT
                assert historical.origin.provider_version == acquired.origin.provider_version
            assert paths[-1].endswith("/items/record/versions/3.0/content")
        assert not client.is_closed
    assert received.count("publisher.sharepoint.com") == (0 if outside_host else 2)
    assert "other.sharepoint.com" not in received


async def test_graph_cancellation_releases_the_request_without_closing_borrowed_client() -> None:
    if find_spec("httpx") is None:
        pytest.skip("Install the sharepoint extra.")
    import httpx  # noqa: PLC0415 - Optional provider fixture.

    from domain_kernel import SharePointReaderAdapter  # noqa: PLC0415 - Optional provider fixture.

    started = asyncio.Event()
    released = asyncio.Event()

    async def respond(request: Request) -> Response:
        assert request.url.path.endswith("/items/approved/children")
        started.set()
        try:
            await asyncio.Future[None]()
        finally:
            released.set()
        raise AssertionError("The host cancelled this outstanding request.")

    config = SharePointReader(
        name="evidence",
        drive_id="drive",
        root_item_id="approved",
        credentials=EntraClientSecret(
            tenant_id="tenant", client_id="client", client_secret=Env(env="GRAPH_TEST_SECRET")
        ),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        reader = SharePointReaderAdapter(config=config, credentials=_Token(), client=client)
        task = asyncio.create_task(
            reader.list_children(
                location=ReaderLocation(reader="evidence", path="."), limits=SourceSelectionLimits()
            )
        )
        _ = await asyncio.wait_for(started.wait(), timeout=5)
        _ = task.cancel()
        with pytest.raises(asyncio.CancelledError):
            _ = await task
        assert released.is_set()
        assert not client.is_closed


async def test_entra_authentication_uses_the_tenant_and_sanitizes_provider_failures() -> None:
    if find_spec("httpx") is None:
        pytest.skip("Install the sharepoint extra.")
    from urllib.parse import parse_qs  # noqa: PLC0415 - Credential fixture.

    import httpx  # noqa: PLC0415 - Optional provider fixture.

    from domain_kernel import EntraClientCredentials  # noqa: PLC0415 - Optional provider fixture.

    requests: list[Request] = []

    def respond(request: Request) -> Response:
        requests.append(request)
        assert request.url.host == "login.microsoftonline.com"
        assert request.url.path == "/test-tenant/oauth2/v2.0/token"
        assert "Authorization" not in request.headers
        form = parse_qs(request.read().decode())
        assert form["scope"] == ["https://graph.microsoft.com/.default"]
        assert form["client_secret"] == ["mocked-input-only"]
        return httpx.Response(401, json={"error_description": "provider-internal-details"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        provider = EntraClientCredentials(
            tenant_id="test-tenant",
            client_id="test-client",
            client_secret=SecretStr("mocked-input-only"),
            client=transport,
        )
        assert requests == []
        with pytest.raises(SourceReadError, match="configured Entra credentials") as error:
            _ = provider.get_token(scope="https://graph.microsoft.com/.default")
        assert "provider-internal-details" not in str(error.value)
        assert len(requests) == 1
        assert not transport.is_closed


async def test_s3_artifact_recovers_only_the_exact_conditional_write(
    *,
    s3_api: S3Client,
) -> None:
    from base64 import b64encode  # noqa: PLC0415 -- Provider contract fixture.

    from botocore.response import StreamingBody  # noqa: PLC0415 -- Selected optional provider.
    from botocore.stub import Stubber  # noqa: PLC0415 -- Selected optional provider.

    from domain_kernel import (  # noqa: PLC0415 -- Selected optional provider.
        ArtifactConflictError,
        ArtifactWrite,
        ProjectId,
        S3ArtifactStore,
    )
    from domain_kernel._shared.domain.record_encoding import record_bytes  # noqa: PLC0415
    from domain_kernel.configuration import S3Store  # noqa: PLC0415

    request = ArtifactWrite(
        project_id=ProjectId(value="recruitment"),
        model_id=None,
        store="artifacts",
        key="projects/recruitment/model.json",
        media_type="application/json",
        expected_hash=hash_bytes(content=_CONTENT),
    )
    stored = S3ArtifactStore(
        config=S3Store(
            name="artifacts",
            bucket="outputs-test",
            prefix="approved/",
            credentials=AwsDefaultChain(),
        ),
        client=s3_api,
    )
    target = {"Bucket": "outputs-test", "Key": "approved/projects/recruitment/model.json"}
    identity = hash_bytes(content=record_bytes(value=request, root_type=ArtifactWrite)).value
    checksum = b64encode(
        bytes.fromhex(request.expected_hash.value.removeprefix("sha256:"))
    ).decode()
    metadata = {"dk-request-hash": identity}
    parameters = {
        **target,
        "Body": _CONTENT,
        "ContentLength": len(_CONTENT),
        "ContentType": request.media_type,
        "IfNoneMatch": "*",
        "ChecksumSHA256": checksum,
        "Metadata": metadata,
    }
    with Stubber(s3_api) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=parameters,
        )
        stub.add_response(
            "get_object",
            {
                "ETag": _ETAG,
                "VersionId": "stable-artifact",
                "ContentLength": len(_CONTENT),
                "Metadata": metadata,
                "ContentType": request.media_type,
                "Body": StreamingBody(BytesIO(_CONTENT), len(_CONTENT)),
            },
            target,
        )
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=parameters,
        )
        stub.add_response(
            "get_object",
            {
                "ETag": _ETAG,
                "VersionId": "stable-artifact",
                "ContentLength": len(_CONTENT),
                "Metadata": {},
                "ContentType": request.media_type,
                "Body": StreamingBody(BytesIO(_CONTENT), len(_CONTENT)),
            },
            target,
        )
        recovered = stored.put(request=request, chunks=[_CONTENT])
        assert recovered.content_hash == request.expected_hash
        assert recovered.provider_version == "version:stable-artifact"
        with pytest.raises(ArtifactConflictError):
            _ = stored.put(request=request, chunks=[_CONTENT])
        stub.assert_no_pending_responses()
