"""AWS credential and connection ownership at the optional provider boundary."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Literal, Protocol, final, override

from domain_kernel.configuration import AwsProfile, AwsStatic
from domain_kernel.shared.errors import MissingCapabilityError, SourceReadError

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from botocore.config import Config
    from mypy_boto3_s3 import S3Client
    from pydantic import SecretStr

    from domain_kernel.configuration import S3Reader, S3Store


@dataclass(frozen=True, kw_only=True)
class AwsCredentialSnapshot:
    """Short-lived signing material owned by an explicit credential provider."""

    access_key_id: SecretStr
    secret_access_key: SecretStr
    session_token: SecretStr | None = None
    expires_at: datetime | None = None


class AwsCredentialProvider(Protocol):
    """Return current signing material without persisting it."""

    def get_credentials(self) -> AwsCredentialSnapshot:
        """Return a usable snapshot for one operation."""
        ...


@final
@dataclass(frozen=True, kw_only=True)
class StaticAwsCredentials(AwsCredentialProvider):
    """Use one explicitly selected environment-backed signing snapshot."""

    snapshot: AwsCredentialSnapshot

    @override
    def get_credentials(self) -> AwsCredentialSnapshot:
        """Return the configured signing material for this binding."""
        return self.snapshot


class _S3Session(Protocol):
    def client(  # noqa: PLR0913 - Match the single typed boto3 service overload.
        self,
        service_name: Literal["s3"],
        *,
        region_name: str | None,
        config: Config,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
    ) -> S3Client: ...


def _aws_session(*, profile: str | None) -> _S3Session:
    try:
        from boto3 import Session  # noqa: PLC0415 - Optional S3 provider.
    except ImportError:
        raise MissingCapabilityError(message="Install the Domain Kernel s3 extra.") from None
    return Session(profile_name=profile)


@final
class S3RequestError(SourceReadError):
    """An actionable provider failure with a safe status for exact recovery."""

    def __init__(self, *, status: int, retryable: bool = False) -> None:
        """Keep provider descriptions out of SDK findings."""
        self.status = status
        super().__init__(
            message=(
                "Check the configured S3 credential and prefix permissions."
                if status in (401, 403)
                else "Check availability of the exact object in the configured S3 binding."
            ),
            retryable=retryable,
        )


def s3_request[T](*, call: Callable[[], T]) -> T:
    """Translate provider failures at the request boundary."""
    try:
        from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415 - Optional S3 provider.
    except ImportError:
        raise MissingCapabilityError(message="Install the Domain Kernel s3 extra.") from None
    try:
        return call()
    except ClientError as error:
        metadata = error.response.get("ResponseMetadata")
        status = 0 if metadata is None else metadata.get("HTTPStatusCode", 0)
        raise S3RequestError(
            status=status,
            retryable=status in (408, 429) or status >= HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from None
    except BotoCoreError:
        raise S3RequestError(status=0) from None


async def run_s3_request[T](*, call: Callable[[], T]) -> T:
    """Release the bounded provider operation before returning cancellation."""
    work = asyncio.create_task(asyncio.to_thread(call))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        with suppress(Exception):
            _ = await work
        raise


@final
class S3Connection:
    """Borrow an injected client or own the client for one bounded AWS operation."""

    def __init__(
        self,
        *,
        config: S3Reader | S3Store,
        credentials: AwsCredentialProvider | None,
        client: S3Client | None,
    ) -> None:
        """Capture explicitly bound signing and client ownership."""
        self._config = config
        self._credentials = credentials
        self._borrowed = client

    def _create(self) -> S3Client:
        try:
            from botocore.config import Config  # noqa: PLC0415 - Optional S3 provider.
        except ImportError:
            raise MissingCapabilityError(message="Install the Domain Kernel s3 extra.") from None
        credentials = self._config.credentials
        profile = credentials.profile if isinstance(credentials, AwsProfile) else None
        session = _aws_session(profile=profile)
        options = Config(
            connect_timeout=5,
            read_timeout=15,
            retries={"mode": "standard", "total_max_attempts": 2},
            signature_version="s3v4",
        )
        if self._credentials is None:
            if isinstance(credentials, AwsStatic):
                raise MissingCapabilityError(
                    message="Resolve the configured static S3 credentials."
                )
            return session.client("s3", region_name=self._config.region, config=options)
        material = self._credentials.get_credentials()
        expiration = material.expires_at
        if expiration is not None and (
            expiration.utcoffset() is None or expiration <= datetime.now(tz=UTC)
        ):
            raise SourceReadError(message="Refresh the configured S3 credentials before retrying.")
        token = material.session_token
        return session.client(
            "s3",
            region_name=self._config.region,
            config=options,
            aws_access_key_id=material.access_key_id.get_secret_value(),
            aws_secret_access_key=material.secret_access_key.get_secret_value(),
            aws_session_token=None if token is None else token.get_secret_value(),
        )

    @contextmanager
    def open(self) -> Generator[S3Client]:
        """Keep a caller-owned client open and always release an owned client."""
        if self._borrowed is not None:
            yield self._borrowed
            return
        client = s3_request(call=self._create)
        try:
            yield client
        finally:
            client.close()
