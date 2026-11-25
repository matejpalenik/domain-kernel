"""Read scoped SharePoint document versions through Microsoft Graph v1.0."""

from __future__ import annotations

import asyncio
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING, Protocol, final, override
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain_kernel.shared.contracts import Page
from domain_kernel.shared.domain.validators.paths import relative_parts
from domain_kernel.shared.errors import (
    MissingCapabilityError,
    ResourceLimitError,
    SourceReadError,
)
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.sources.application.contracts import ReaderLocation, SourceEntry, SourceEntryKind
from domain_kernel.sources.application.ports import AcquiredSource, SourceBuffer, SourceReader
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.models import FileOrigin
from domain_kernel.sources.infrastructure.remote_listing import (
    listing_binding,
    next_page,
    read_continuation,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import ClassVar
    from urllib.parse import SplitResult

    from httpx import AsyncClient, Response
    from pydantic import SecretStr

    from domain_kernel.configuration import SharePointReader, SourceSelectionLimits
    from domain_kernel.shared.identifiers.page_cursor import PageCursor
    from domain_kernel.sources.domain.models import ProcessingLimits, SourceRevision


_GRAPH = "https://graph.microsoft.com"
_SCOPE = _GRAPH + "/.default"
_METADATA_LIMIT = 2 * 1024 * 1024
_MAX_ITEM_ID_LENGTH = 1024
_FIELDS = "id,name,eTag,size,file,folder,remoteItem,webUrl,parentReference"
_NONPUBLIC = frozenset({"localhost"})


class EntraTokenProvider(Protocol):
    """Obtain a Graph token for one explicitly approved scope."""

    def get_token(self, *, scope: str) -> SecretStr:
        """Return a token without any persistent SDK representation."""
        ...


@final
class _GraphRequestError(SourceReadError):
    def __init__(self, *, status: int) -> None:
        self.status = status
        super().__init__(
            message=(
                "Check Graph access to the configured SharePoint drive and folder."
                if status in (401, 403)
                else "Check availability of the exact selected SharePoint item."
            ),
            retryable=status in (408, 429) or status >= HTTPStatus.INTERNAL_SERVER_ERROR,
        )


class _Parent(BaseModel):
    id: str
    drive_id: str = Field(alias="driveId")


class _Item(BaseModel):
    id: str
    name: str
    etag: str | None = Field(default=None, alias="eTag")
    size: int = 0
    file: dict[str, object] | None = None
    folder: dict[str, object] | None = None
    remote: dict[str, object] | None = Field(default=None, alias="remoteItem")
    url: str | None = Field(default=None, alias="webUrl")
    parent: _Parent | None = Field(default=None, alias="parentReference")

    @property
    def kind(self) -> SourceEntryKind:
        if self.remote is not None:
            return SourceEntryKind.LINK
        if self.folder is not None and self.file is None:
            return SourceEntryKind.FOLDER
        return SourceEntryKind.FILE if self.file is not None else SourceEntryKind.LINK


class _Children(BaseModel):
    value: list[_Item]
    next_link: str | None = Field(default=None, alias="@odata.nextLink")


class _Version(BaseModel):
    id: str


class _Versions(BaseModel):
    value: list[_Version]


class _Pin(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)
    item_id: str
    etag: str
    version_id: str | None


def _decode[T: BaseModel](*, payload: bytes, model: type[T]) -> T:
    try:
        return model.model_validate_json(payload, strict=True)
    except ValidationError:
        raise SourceReadError(message="Graph returned an invalid SharePoint response.") from None


def _header(*, response: Response, name: str) -> str | None:
    return next((value for key, value in response.headers.items() if key == name), None)


async def _read(*, response: Response, limit: int) -> bytes:
    length = _header(response=response, name="content-length")
    if length is not None and (not length.isdecimal() or int(length) > limit):
        raise ResourceLimitError(message="Select a SharePoint response within the byte limit.")
    payload = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65_536):
        if len(payload) + len(chunk) > limit:
            raise ResourceLimitError(message="Select a SharePoint response within the byte limit.")
        payload.extend(chunk)
    return bytes(payload)


def _page_url(*, url: str, route: str) -> str:
    captured = _split_url(url=url)
    if (
        captured.scheme != "https"
        or captured.netloc != "graph.microsoft.com"
        or captured.path != route
        or not captured.query
        or captured.fragment
    ):
        raise SourceReadError(message="Graph returned a continuation outside the selected folder.")
    return url


def _download_url(*, url: str, item_url: str | None) -> str:
    selected = _split_url(url=url)
    origin = None if item_url is None else _split_url(url=item_url)
    host = selected.hostname
    if (
        origin is None
        or origin.scheme != "https"
        or selected.scheme != "https"
        or host is None
        or host in _NONPUBLIC
        or not host.endswith(
            (".sharepoint.com", ".sharepoint.us", ".sharepoint.cn", ".sharepoint.de")
        )
        or selected.netloc != host
        or origin.hostname != host
        or selected.fragment
    ):
        raise SourceReadError(
            message="Graph returned a download outside the item's SharePoint host."
        )
    return url


def _split_url(*, url: str) -> SplitResult:
    try:
        return urlsplit(url=url)
    except ValueError:
        raise SourceReadError(message="Graph returned an invalid SharePoint address.") from None


async def _request(  # noqa: PLR0913 - Bind the exact URL, auth and resource limit explicitly.
    *,
    client: AsyncClient,
    url: str,
    token: str | None,
    limit: int,
    allow_redirect: bool = False,
    params: dict[str, str] | None = None,
) -> tuple[bytes, str | None]:
    from httpx import InvalidURL, Request, TransportError  # noqa: PLC0415 - Optional Graph transport.

    headers = {"Accept-Encoding": "identity"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    try:
        request = Request(method="GET", url=url, headers=headers, params=params)
        response = await client.send(request, auth=None, stream=True, follow_redirects=False)
        async with aclosing(response):
            if allow_redirect and response.status_code == HTTPStatus.FOUND:
                redirect = _header(response=response, name="location")
                if not redirect:
                    raise SourceReadError(message="Graph did not identify the approved download.")
                return b"", redirect
            if response.status_code != HTTPStatus.OK:
                raise _GraphRequestError(status=response.status_code)
            return await _read(response=response, limit=limit), None
    except TransportError:
        raise SourceReadError(
            message="Retry the bounded request to the configured SharePoint service.",
            retryable=True,
        ) from None
    except InvalidURL:
        raise SourceReadError(message="Graph returned an invalid SharePoint address.") from None


@final
class SharePointReaderAdapter(SourceReader):
    """Acquire approved documents and bounded folder pages through Graph."""

    def __init__(
        self,
        *,
        config: SharePointReader,
        credentials: EntraTokenProvider,
        client: AsyncClient | None = None,
    ) -> None:
        """Bind a drive and folder and optionally borrow the host's HTTP client."""
        self._config = config
        self._credentials = credentials
        self._client = client
        self._scope = hash_json(
            value=("sharepoint", config.name, config.drive_id, config.root_item_id)
        ).value
        self._items = "/v1.0/drives/" + quote(config.drive_id, safe="") + "/items/"

    @property
    @override
    def provider_scope(self) -> str:
        """Return the exact noncredential Graph binding."""
        return self._scope

    @asynccontextmanager
    async def _connection(self) -> AsyncGenerator[AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        try:
            from httpx import AsyncClient  # noqa: PLC0415 - Optional Graph transport.
        except ImportError:
            raise MissingCapabilityError(
                message="Install the Domain Kernel sharepoint extra."
            ) from None
        async with AsyncClient(timeout=15.0, follow_redirects=False, trust_env=False) as client:
            yield client

    def _relative(self, *, location: ReaderLocation, allow_root: bool = False) -> tuple[str, ...]:
        if location.reader != self._config.name:
            raise SourceReadError(message="Select a location in this configured SharePoint reader.")
        return relative_parts(path=location.path, allow_root=allow_root)

    def _item_route(self, *, item_id: str) -> str:
        if not item_id or len(item_id) > _MAX_ITEM_ID_LENGTH:
            raise SourceReadError(message="Graph returned an invalid item identity.")
        return self._items + quote(item_id, safe="")

    def _require_child(self, *, item: _Item, parent_id: str) -> None:
        parent = item.parent
        if (
            parent is None
            or parent.drive_id != self._config.drive_id
            or parent.id != parent_id
            or item.name in ("", ".", "..")
            or "/" in item.name
        ):
            raise SourceReadError(message="Graph returned an item outside the configured folder.")

    async def _resolve(self, *, parts: tuple[str, ...], client: AsyncClient, token: str) -> _Item:
        parent = self._config.root_item_id
        item: _Item | None = None
        for index, name in enumerate(parts):
            route = self._item_route(item_id=parent) + ":/" + quote(name, safe="")
            payload, _ = await _request(
                client=client,
                url=_GRAPH + route,
                token=token,
                limit=_METADATA_LIMIT,
                params={"$select": _FIELDS},
            )
            item = _decode(payload=payload, model=_Item)
            self._require_child(item=item, parent_id=parent)
            if item.name != name or (
                index + 1 < len(parts) and item.kind is not SourceEntryKind.FOLDER
            ):
                raise SourceReadError(
                    message="Select the exact named child under the approved folder."
                )
            parent = item.id
        if item is None:
            raise SourceReadError(message="Select a file or contained child folder.")
        return item

    @override
    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]:
        """Page through immediate children of the inspected approved folder."""
        parts = self._relative(location=location, allow_root=True)
        binding = listing_binding(scope=self._scope, location=location, limits=limits, limit=limit)
        continuation = read_continuation(cursor=cursor, binding=binding)
        token = (
            await asyncio.to_thread(self._credentials.get_token, scope=_SCOPE)
        ).get_secret_value()
        async with self._connection() as connection:
            folder = self._config.root_item_id
            if parts:
                selected = await self._resolve(parts=parts, client=connection, token=token)
                if selected.kind is not SourceEntryKind.FOLDER:
                    raise SourceReadError(message="Select a SharePoint folder for enumeration.")
                folder = selected.id
            route = self._item_route(item_id=folder) + "/children"
            url = (
                _GRAPH + route if continuation is None else _page_url(url=continuation, route=route)
            )
            payload, _ = await _request(
                client=connection,
                url=url,
                token=token,
                limit=_METADATA_LIMIT,
                params={"$select": _FIELDS, "$top": str(limit)} if continuation is None else None,
            )
        children = _decode(payload=payload, model=_Children)
        if len(children.value) > limit or len({item.name for item in children.value}) != len(
            children.value
        ):
            raise SourceReadError(message="Graph returned an invalid or overfull page of children.")
        entries: list[SourceEntry] = []
        for item in children.value:
            self._require_child(item=item, parent_id=folder)
            entries.append(
                SourceEntry(
                    location=ReaderLocation(
                        reader=self._config.name, path="/".join((*parts, item.name))
                    ),
                    kind=item.kind,
                    provider_scope=self._scope,
                    provider_item_id=item.id,
                    provider_version=item.etag,
                )
            )
        next_link = children.next_link
        if next_link is not None:
            next_link = _page_url(url=next_link, route=route)
            if next_link == continuation:
                raise SourceReadError(message="Graph did not advance its listing continuation.")
        return Page(items=entries, next_cursor=next_page(token=next_link, binding=binding))

    async def _current_pin(self, *, connection: AsyncClient, item: _Item, token: str) -> _Pin:
        if item.kind is not SourceEntryKind.FILE or not item.etag:
            raise SourceReadError(message="Select a file with an inspected Graph revision.")
        payload, _ = await _request(
            client=connection,
            url=_GRAPH + self._item_route(item_id=item.id) + "/versions",
            token=token,
            limit=_METADATA_LIMIT,
        )
        versions = _decode(payload=payload, model=_Versions).value
        return _Pin(
            item_id=item.id, etag=item.etag, version_id=versions[0].id if versions else None
        )

    async def _download(  # noqa: PLR0913 - Bind the exact inspected revision and stream budget.
        self,
        *,
        connection: AsyncClient,
        item: _Item,
        current: _Pin,
        selected: _Pin,
        token: str,
        limit: int,
    ) -> bytes:
        route = self._item_route(item_id=item.id)
        if selected != current:
            if selected.version_id is None or selected.version_id == current.version_id:
                raise SourceRevisionMismatchError
            route += "/versions/" + quote(selected.version_id, safe="")
        elif item.size > limit:
            raise ResourceLimitError(message="Select a SharePoint document within the byte limit.")
        payload, redirect = await _request(
            client=connection,
            url=_GRAPH + route + "/content",
            token=token,
            limit=limit,
            allow_redirect=True,
        )
        if redirect is not None:
            payload, _ = await _request(
                client=connection,
                url=_download_url(url=redirect, item_url=item.url),
                token=None,
                limit=limit,
            )
        return payload

    def _expected_pin(
        self, *, location: ReaderLocation, expected: SourceRevision | None
    ) -> _Pin | None:
        if expected is None:
            return None
        origin = expected.origin
        if (
            not isinstance(origin, FileOrigin)
            or (origin.reader, origin.provider_scope, origin.location)
            != (location.reader, self._scope, location.path)
            or origin.provider_version is None
        ):
            raise SourceRevisionMismatchError
        try:
            return _Pin.model_validate_json(origin.provider_version)
        except ValidationError:
            raise SourceRevisionMismatchError from None

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
        """Read and verify the approved exact document revision in a bounded buffer."""
        parts = self._relative(location=location)
        pin = self._expected_pin(location=location, expected=expected)
        if expected_entry is not None and (
            expected_entry.location != location
            or expected_entry.provider_scope != self._scope
            or expected_entry.kind is not SourceEntryKind.FILE
        ):
            raise SourceRevisionMismatchError
        token = (
            await asyncio.to_thread(self._credentials.get_token, scope=_SCOPE)
        ).get_secret_value()
        try:
            async with self._connection() as connection:
                item = await self._resolve(parts=parts, client=connection, token=token)
                current = await self._current_pin(connection=connection, item=item, token=token)
                if expected_entry is not None and (
                    expected_entry.provider_item_id != current.item_id
                    or expected_entry.provider_version != current.etag
                ):
                    raise SourceRevisionMismatchError
                chosen = current if pin is None else pin
                if chosen.item_id != current.item_id:
                    raise SourceRevisionMismatchError
                data = await self._download(
                    connection=connection,
                    item=item,
                    current=current,
                    selected=chosen,
                    token=token,
                    limit=limits.max_source_bytes,
                )
                if chosen == current:
                    refreshed = await self._resolve(parts=parts, client=connection, token=token)
                    if (refreshed.id, refreshed.etag, refreshed.size) != (
                        item.id,
                        item.etag,
                        len(data),
                    ):
                        raise SourceRevisionMismatchError
        except _GraphRequestError as error:
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
                    location=location.path,
                    provider_version=chosen.model_dump_json(),
                    acquired_at=datetime.now(tz=UTC),
                ),
                byte_length=len(data),
                content_hash=digest,
            )
