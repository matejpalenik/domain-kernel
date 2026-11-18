"""Private, local provider response journal for offline validation and recovery."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from pydantic import TypeAdapter

from domain_kernel._shared.application.inference import (
    ModelGateway,
    ModelResponse,
    TruncatedResponse,
    TruncatedResponseError,
)
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.hashing import hash_bytes, hash_json
from domain_kernel.shared.validation import require_text

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel._shared.application.inference import ModelRequest


@dataclass(frozen=True, kw_only=True)
class LocalReplayGateway(ModelGateway):
    """Record with a provider, or replay an exact request when no provider is supplied."""

    path: Path
    profile: str
    gateway: ModelGateway | None = field(default=None, repr=False)
    retain_responses: bool = True

    def __post_init__(self) -> None:
        """Require a stable profile for all parameters that can change provider output."""
        require_text(value=self.profile, field="Versioned provider configuration")

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

    def _reserve(self, *, key: str) -> ModelResponse | None:
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
            if hash_bytes(content=payload).value != digest:
                raise InferenceError(message="The local response failed its integrity check.")
            stored = _RESPONSE.validate_json(payload)
            if isinstance(stored, TruncatedResponse):
                raise TruncatedResponseError(response=stored)
            return stored

    def _finish(self, *, key: str, response: ModelResponse | TruncatedResponse) -> None:
        payload = _RESPONSE.dump_json(response)
        with closing(self._open()) as connection, connection:
            _ = connection.execute(
                "UPDATE responses SET digest=?, payload=? WHERE key=? AND digest IS NULL",
                (
                    hash_bytes(content=payload).value,
                    payload if self.retain_responses else None,
                    key,
                ),
            )

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Reserve before dispatch and capture returned bytes before semantic validation."""
        key = hash_json(
            value=record_value(
                value=(
                    self.profile,
                    request.scope,
                    request.instructions,
                    request.response_schema_json,
                    request.context_json,
                    tuple((part.text, part.evidence) for part in request.inputs),
                )
            )
        ).value
        cached = await asyncio.to_thread(self._reserve, key=key)
        if cached is not None:
            return cached
        if self.gateway is None:
            raise InferenceError(message="Configure a provider for capture.")
        try:
            response = await self.gateway.generate(request=request)
        except TruncatedResponseError as error:
            await asyncio.to_thread(self._finish, key=key, response=error.response)
            raise
        await asyncio.to_thread(self._finish, key=key, response=response)
        return response


_RESPONSE = TypeAdapter(ModelResponse | TruncatedResponse)
