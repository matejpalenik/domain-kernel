"""Private, local provider response journal for offline validation and recovery."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from pydantic import TypeAdapter

from domain_kernel.discovery.application.contracts.model_response import ModelResponse
from domain_kernel.discovery.application.contracts.truncated_response import TruncatedResponse
from domain_kernel.discovery.application.errors.inference_error import InferenceError
from domain_kernel.discovery.application.errors.inference_timeout_error import InferenceTimeoutError
from domain_kernel.discovery.application.errors.truncated_response_error import (
    TruncatedResponseError,
)
from domain_kernel.discovery.application.ports import SchemaDiscoveryGateway
from domain_kernel.discovery.application.protocols.model_gateway import ModelGateway
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel.discovery.application.contracts.model_request import ModelRequest


@dataclass(frozen=True, kw_only=True)
class _TimedOutResponse:
    """The local deadline elapsed and provider usage remains unknown."""

    timeout_seconds: float


def _read_response(*, digest: str, payload: bytes) -> ModelResponse:
    if Hashing.hash_bytes(content=payload).value != digest:
        raise InferenceError(message="The local response failed its integrity check.")
    stored = _RESPONSE.validate_json(payload)
    if isinstance(stored, TruncatedResponse):
        raise TruncatedResponseError(response=stored)
    if isinstance(stored, _TimedOutResponse):
        raise InferenceTimeoutError(timeout_seconds=stored.timeout_seconds)
    return stored


@dataclass(frozen=True, kw_only=True)
class LocalReplayGateway(ModelGateway):
    """Record with a provider, or replay an exact request when no provider is supplied."""

    path: Path
    profile: str
    gateway: ModelGateway | None = field(default=None, repr=False)
    retain_responses: bool = True
    max_attempts: int = 1

    def __post_init__(self) -> None:
        """Require a stable profile for all parameters that can change provider output."""
        TextValidation.require_text(value=self.profile, field="Versioned provider configuration")
        RuntimeTypeValidation.require_exact(
            value=self.max_attempts, expected=int, field="Provider attempts"
        )
        if self.max_attempts < 1:
            raise ValueError("Allow at least one provider attempt.")

    @property
    def supports_schema_discovery(self) -> bool:
        """Allow exact offline replay or pass through a compatible provider."""
        return self.gateway is None or (
            isinstance(self.gateway, SchemaDiscoveryGateway)
            and self.gateway.supports_schema_discovery
        )

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(descriptor).st_mode & 0o077:
                raise InferenceError(message="Use an owner-only response journal.")
        finally:
            os.close(descriptor)
        connection = sqlite3.connect(self.path)
        _ = connection.execute(
            "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, digest TEXT, payload BLOB)"
        )
        return connection

    def _reserve(self, *, key: str, retry_cancelled: bool) -> ModelResponse | None:
        with closing(self._open()) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row: object = (
                connection.execute(
                    "SELECT digest, payload FROM responses WHERE key=?", (key,)
                ).fetchone()
                or None
            )
            if row is None:
                if self.gateway is None:
                    raise InferenceError(message="No exact response in the local replay journal.")
                _ = connection.execute("INSERT INTO responses(key) VALUES (?)", (key,))
                return None
            match row:
                case ("cancelled", None) if retry_cancelled and self.gateway is not None:
                    _ = connection.execute(
                        "UPDATE responses SET digest=NULL WHERE key=? AND digest='cancelled'",
                        (key,),
                    )
                    return None
                case (None, None):
                    raise InferenceError(
                        message="A provider attempt is unresolved. Reconcile it before retrying."
                    )
                case (str() as digest, bytes() as payload):
                    pass
                case (str(), None):
                    raise InferenceError(message="Only the response fingerprint was retained.")
                case _:
                    raise InferenceError(message="Inspect the damaged local response journal.")
            if not self.retain_responses:
                raise InferenceError(
                    message="Only response fingerprints are available in this mode."
                )
            return _read_response(digest=digest, payload=payload)

    def _finish(
        self, *, key: str, response: ModelResponse | TruncatedResponse | _TimedOutResponse
    ) -> None:
        payload = _RESPONSE.dump_json(response)
        with closing(self._open()) as connection, connection:
            _ = connection.execute(
                "UPDATE responses SET digest=?, payload=? WHERE key=? AND digest IS NULL",
                (
                    Hashing.hash_bytes(content=payload).value,
                    payload if self.retain_responses else None,
                    key,
                ),
            )

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Reserve before dispatch and capture returned bytes before semantic validation."""
        key = Hashing.hash_json(
            value=RecordCodec.to_value(
                value=(
                    self.profile,
                    request.scope,
                    request.instructions,
                    request.response_schema_json,
                    request.context_json,
                    tuple((part.text, part.evidence) for part in request.inputs),
                    *(
                        (request.max_output_tokens,)
                        if request.max_output_tokens is not None
                        else ()
                    ),
                    *(("provider-output-limit",) if request.use_provider_output_limit else ()),
                )
            )
        ).value
        cached = await self._reservation(key=key, retry_cancelled=request.retry_cancelled)
        if cached is not None:
            return cached
        if self.gateway is None:
            raise InferenceError(message="Configure a provider for capture.")
        try:
            response = await self._dispatch(request=request, gateway=self.gateway)
        except TruncatedResponseError as error:
            await asyncio.to_thread(self._finish, key=key, response=error.response)
            raise
        except (InferenceTimeoutError, TimeoutError) as error:
            if self.retain_responses:
                seconds = (
                    error.timeout_seconds
                    if isinstance(error, InferenceTimeoutError)
                    else request.timeout_seconds
                )
                await asyncio.to_thread(
                    self._finish, key=key, response=_TimedOutResponse(timeout_seconds=seconds)
                )
            raise
        except asyncio.CancelledError:
            if request.retry_cancelled:
                await asyncio.to_thread(self._cancelled, key=key)
            raise
        await asyncio.to_thread(self._finish, key=key, response=response)
        return response

    async def _dispatch(self, *, request: ModelRequest, gateway: ModelGateway) -> ModelResponse:
        # Keep ownership of the reservation across approved retries. A completed
        # or truncated response still becomes a receipt and a cancelled task exits.
        delay = 1.0
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await gateway.generate(request=request)
            except (InferenceError, TimeoutError) as error:
                if attempt == self.max_attempts or (
                    isinstance(error, InferenceError) and not error.retryable
                ):
                    raise
                _LOGGER.info("Retrying provider request after attempt %d", attempt)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        raise AssertionError("The journal must allow at least one provider attempt.")

    async def _reservation(self, *, key: str, retry_cancelled: bool) -> ModelResponse | None:
        if not retry_cancelled:
            return await asyncio.to_thread(self._reserve, key=key, retry_cancelled=False)
        reservation = asyncio.create_task(
            asyncio.to_thread(self._reserve, key=key, retry_cancelled=True)
        )
        try:
            return await asyncio.shield(reservation)
        except asyncio.CancelledError:
            # A cancelled waiter can leave the SQLite reservation thread running.
            # If it took ownership, release it before propagating the cancellation.
            try:
                cached = await reservation
            except InferenceError:
                pass
            else:
                if cached is None:
                    await asyncio.to_thread(self._cancelled, key=key)
            raise

    def _cancelled(self, *, key: str) -> None:
        with closing(self._open()) as connection, connection:
            _ = connection.execute(
                "UPDATE responses SET digest='cancelled' WHERE key=? AND digest IS NULL", (key,)
            )


_RESPONSE = TypeAdapter(ModelResponse | TruncatedResponse | _TimedOutResponse)
