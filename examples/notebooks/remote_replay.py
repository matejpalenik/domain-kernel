"""Mock provider responses for the real cloud adapter acquisition and export journey."""

from __future__ import annotations

from base64 import b64encode
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

from botocore.response import StreamingBody
from botocore.stub import Stubber
from httpx import AsyncClient, MockTransport, Response
from pydantic import SecretStr

from domain_kernel import (
    ArtifactWrite,
    AwsCredentialSnapshot,
    ClientIntegrations,
    DoclingParser,
    S3ArtifactStore,
    S3ReaderAdapter,
    SharePointReaderAdapter,
)
from domain_kernel.configuration import (
    AwsDefaultChain,
    EntraClientSecret,
    Env,
    S3Reader,
    S3Store,
    SharePointReader,
)
from domain_kernel.shared.domain.codecs.record_encoding import record_bytes
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.sources.infrastructure.aws import S3Connection, StaticAwsCredentials

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from httpx import Request

    from domain_kernel import DomainModelBundle


S3_INPUT = "e9-s3-input"
GRAPH_INPUT = "e9-sharepoint"
ARTIFACTS = "e9-s3-artifacts"
EXPORT_PATH = "recruitment-bundle.json"
_S3_KEY = "approved/references/eli-metadata-selection.csv"
_ETAG = '"provider-token"'
_INPUT_BUCKET = "notebook-inputs"
_OUTPUT_BUCKET = "notebook-outputs"
_GRAPH_ROOT = "/v1.0/drives/approved-drive/items/"
_FILE = "eli-metadata-selection.csv"


class _MockGraphCredentials:
    def get_token(self, *, scope: str) -> SecretStr:
        if scope != "https://graph.microsoft.com/.default":
            raise ValueError("The replay is scoped to Microsoft Graph.")
        return SecretStr("mocked-graph-token")


def _credentials(*, binding: str) -> StaticAwsCredentials:
    return StaticAwsCredentials(
        snapshot=AwsCredentialSnapshot(
            access_key_id=SecretStr(f"mocked-{binding}-access"),
            secret_access_key=SecretStr(f"mocked-{binding}-secret"),
        )
    )


def _s3_source(*, stub: Stubber, corpus: bytes) -> None:
    root = {"Bucket": _INPUT_BUCKET, "Prefix": "approved/", "Delimiter": "/", "MaxKeys": 1}
    stub.add_response(
        "list_objects_v2",
        {
            "IsTruncated": True,
            "NextContinuationToken": "next",
            "CommonPrefixes": [{"Prefix": "approved/references/"}],
        },
        root,
    )
    stub.add_response(
        "list_objects_v2",
        {"IsTruncated": False, "CommonPrefixes": [{"Prefix": "approved/updates/"}]},
        {**root, "ContinuationToken": "next"},
    )
    stub.add_response(
        "list_objects_v2",
        {"IsTruncated": False, "Contents": [{"Key": _S3_KEY, "ETag": _ETAG, "Size": len(corpus)}]},
        {**root, "Prefix": "approved/references/"},
    )
    target = {"Bucket": _INPUT_BUCKET, "Key": _S3_KEY}
    metadata = {"ContentLength": len(corpus), "ETag": _ETAG, "VersionId": "source-1"}
    stub.add_response("head_object", metadata, target)
    stub.add_response(
        "get_object",
        {**metadata, "Body": StreamingBody(BytesIO(corpus), len(corpus))},
        {**target, "VersionId": "source-1", "IfMatch": _ETAG},
    )


def _s3_output(*, stub: Stubber, publication: DomainModelBundle) -> None:
    content = publication.serialize()
    digest = hash_bytes(content=content)
    request = ArtifactWrite(
        project_id=publication.scope.project_id,
        model_id=publication.scope.model_id,
        store=ARTIFACTS,
        key=f"projects/{publication.scope.project_id.value}/{EXPORT_PATH}",
        media_type="application/json",
        expected_hash=digest,
    )
    metadata = {
        "dk-request-hash": hash_bytes(
            content=record_bytes(value=request, root_type=ArtifactWrite)
        ).value
    }
    checksum = b64encode(bytes.fromhex(digest.value.removeprefix("sha256:"))).decode()
    target = {"Bucket": _OUTPUT_BUCKET, "Key": f"exports/{request.key}"}
    stub.add_response(
        "put_object",
        {"VersionId": "versioned-notebook-export", "ETag": _ETAG},
        {
            **target,
            "Body": content,
            "ContentLength": len(content),
            "ContentType": request.media_type,
            "Metadata": metadata,
            "ChecksumSHA256": checksum,
            "IfNoneMatch": "*",
        },
    )
    stub.add_response(
        "get_object",
        {
            "VersionId": "versioned-notebook-export",
            "ETag": _ETAG,
            "ContentType": request.media_type,
            "ContentLength": len(content),
            "Metadata": metadata,
            "Body": StreamingBody(BytesIO(content), len(content)),
        },
        {**target, "VersionId": "versioned-notebook-export"},
    )


@dataclass(frozen=True, kw_only=True)
class _GraphResponse:
    corpus: bytes

    def __call__(self, request: Request) -> Response:
        if request.url.host == "notebook.sharepoint.com" and "Authorization" not in request.headers:
            return Response(200, content=self.corpus)
        if request.headers.get("Authorization") != "Bearer mocked-graph-token":
            return Response(403)
        route = request.url.path
        item = {
            "id": "eli",
            "name": _FILE,
            "eTag": _ETAG,
            "size": len(self.corpus),
            "file": {"mimeType": "text/csv"},
            "webUrl": f"https://notebook.sharepoint.com/documents/{_FILE}",
            "parentReference": {"driveId": "approved-drive", "id": "approved-folder"},
        }
        if route == _GRAPH_ROOT + "eli/content":
            return Response(302, headers={"Location": "https://notebook.sharepoint.com/download"})
        metadata = {
            _GRAPH_ROOT + "approved-folder/children": {"value": [item]},
            _GRAPH_ROOT + f"approved-folder:/{_FILE}": item,
            _GRAPH_ROOT + "eli/versions": {"value": [{"id": "1.0"}]},
        }.get(route)
        return Response(404) if metadata is None else Response(200, json=metadata)


@dataclass(frozen=True, kw_only=True)
class Replay:
    """Provider bindings for remote acquisition and export."""

    s3: S3ReaderAdapter
    sharepoint: SharePointReaderAdapter
    integrations: ClientIntegrations


@asynccontextmanager
async def mocked_cloud(*, corpus: bytes, publication: DomainModelBundle) -> AsyncGenerator[Replay]:
    """Bind real production adapters to scoped, scripted provider responses."""
    source = S3Reader(
        name=S3_INPUT,
        bucket=_INPUT_BUCKET,
        prefix="approved/",
        region="eu-central-1",
        credentials=AwsDefaultChain(),
    )
    destination = S3Store(
        name=ARTIFACTS,
        bucket=_OUTPUT_BUCKET,
        prefix="exports/",
        region="eu-central-1",
        credentials=AwsDefaultChain(),
    )
    graph = SharePointReader(
        name=GRAPH_INPUT,
        drive_id="approved-drive",
        root_item_id="approved-folder",
        credentials=EntraClientSecret(
            tenant_id="mock-tenant", client_id="mock-client", client_secret=Env(env="DK_MOCK_GRAPH")
        ),
    )
    inbound = S3Connection(config=source, credentials=_credentials(binding="input"), client=None)
    outbound = S3Connection(
        config=destination, credentials=_credentials(binding="output"), client=None
    )
    with (
        inbound.open() as input_api,
        outbound.open() as output_api,
        Stubber(input_api) as input_stub,
        Stubber(output_api) as output_stub,
    ):
        _s3_source(stub=input_stub, corpus=corpus)
        _s3_output(stub=output_stub, publication=publication)
        async with AsyncClient(transport=MockTransport(_GraphResponse(corpus=corpus))) as transport:
            s3 = S3ReaderAdapter(config=source, client=input_api)
            sharepoint = SharePointReaderAdapter(
                config=graph, credentials=_MockGraphCredentials(), client=transport
            )
            store = S3ArtifactStore(config=destination, client=output_api)
            yield Replay(
                s3=s3,
                sharepoint=sharepoint,
                integrations=ClientIntegrations(
                    source_readers={S3_INPUT: s3, GRAPH_INPUT: sharepoint},
                    format_parsers={"csv": DoclingParser()},
                    artifact_stores={ARTIFACTS: store},
                ),
            )
        input_stub.assert_no_pending_responses()
        output_stub.assert_no_pending_responses()
