"""Obtain and refresh a tenant-bound Graph token through Entra client credentials."""

from __future__ import annotations

from contextlib import closing
from http import HTTPStatus
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, final, override
from urllib.parse import quote

from pydantic import BaseModel, SecretStr, ValidationError

from domain_kernel.shared.errors import MissingCapabilityError, ResourceLimitError, SourceReadError
from domain_kernel.shared.validation import require_text
from domain_kernel.sources.infrastructure.sharepoint_reader import EntraTokenProvider

if TYPE_CHECKING:
    from httpx import Client


_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
_REFRESH_MARGIN_SECONDS = 30


class _TokenResponse(BaseModel):
    token_type: str
    access_token: SecretStr
    expires_in: int


@final
class EntraClientCredentials(EntraTokenProvider):
    """Obtain a token lazily and retain only its short-lived in-memory value."""

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: SecretStr,
        client: Client | None = None,
    ) -> None:
        """Bind the exact Entra tenant and optional caller-owned HTTP client."""
        require_text(value=tenant_id, field="Entra tenant")
        require_text(value=client_id, field="Entra client identity")
        self._url = (
            "https://login.microsoftonline.com/" + quote(tenant_id, safe="") + "/oauth2/v2.0/token"
        )
        self._identifier = client_id
        self._secret = client_secret
        self._client = client
        self._lock = Lock()
        self._token: SecretStr | None = None
        self._expires = 0.0

    @override
    def get_token(self, *, scope: str) -> SecretStr:
        """Refresh a single scoped token on demand before its usable expiry."""
        if scope != _GRAPH_SCOPE:
            raise SourceReadError(
                message="Request only the configured Microsoft Graph token scope."
            )
        with self._lock:
            if self._token is not None and monotonic() < self._expires:
                return self._token
            if self._client is not None:
                response = self._request(client=self._client, scope=scope)
            else:
                try:
                    from httpx import Client as HttpClient  # noqa: PLC0415 - Optional Graph transport.
                except ImportError:
                    raise MissingCapabilityError(
                        message="Install the Domain Kernel sharepoint extra."
                    ) from None
                with HttpClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
                    response = self._request(client=client, scope=scope)
            self._token = response.access_token
            self._expires = monotonic() + max(0, response.expires_in - _REFRESH_MARGIN_SECONDS)
            return self._token

    def _request(self, *, client: Client, scope: str) -> _TokenResponse:
        from httpx import Request, TransportError  # noqa: PLC0415 - Optional Graph transport.

        request = Request(
            method="POST",
            url=self._url,
            data={
                "client_id": self._identifier,
                "client_secret": self._secret.get_secret_value(),
                "scope": scope,
                "grant_type": "client_credentials",
            },
        )
        try:
            with closing(
                client.send(request, auth=None, follow_redirects=False, stream=True)
            ) as response:
                if response.status_code != HTTPStatus.OK:
                    raise SourceReadError(
                        message="Check the configured Entra credentials and Graph consent.",
                        retryable=response.status_code == HTTPStatus.TOO_MANY_REQUESTS
                        or response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                buffer = bytearray()
                for chunk in response.iter_bytes(chunk_size=_MAX_TOKEN_RESPONSE_BYTES + 1):
                    if len(buffer) + len(chunk) > _MAX_TOKEN_RESPONSE_BYTES:
                        raise ResourceLimitError(
                            message="Entra returned an excessive token response."
                        )
                    buffer.extend(chunk)
            token = _TokenResponse.model_validate_json(buffer, strict=True)
        except (TransportError, ValidationError):
            raise SourceReadError(
                message="Check the configured Entra token endpoint and response."
            ) from None
        if (
            token.token_type.casefold() != "bearer"
            or token.expires_in < 1
            or not token.access_token.get_secret_value().strip()
        ):
            raise SourceReadError(
                message="Request a usable bearer token for the configured Graph scope."
            )
        return token
