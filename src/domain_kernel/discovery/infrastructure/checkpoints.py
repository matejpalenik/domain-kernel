"""Private content-addressed state objects and atomic, run-scoped graph checkpoints."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import final

from pydantic import BaseModel

from domain_kernel.discovery.application.claim_extraction import Alias, BatchResult, Finding  # noqa: TC001 -- Pydantic resolves runtime schemas
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.hashing import hash_bytes

_SHA256_HEX_LENGTH = 64


class Receipt(BaseModel):
    """Provider metadata retained independently of untrusted response content."""

    model_id: str
    provider_endpoint: str | None
    input_tokens: int | None
    output_tokens: int | None


class Checkpoint(BaseModel):
    """An immutable stage snapshot referenced by the run's small completion pointer."""

    stage: str
    batches: list[BatchResult]
    aliases: dict[str, Alias]
    edge_findings: dict[str, Finding]
    receipts: list[Receipt]


def write_private(*, path: Path, payload: bytes) -> None:
    """Publish complete owner-only bytes atomically."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        _ = stream.write(payload)
    temporary = Path(stream.name)
    try:
        _ = temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@final
class StageCheckpoints:
    """Resume a graph only against the same scope, revision and processing intent."""

    def __init__(self, *, directory: Path, key: str) -> None:
        """Select a private content-addressed object store and run pointer."""
        self._directory = directory
        self._pointer = directory / key

    def save(self, *, checkpoint: Checkpoint) -> None:
        """Publish state before advancing its pointer."""
        payload = checkpoint.model_dump_json().encode()
        digest = hash_bytes(content=payload).value.removeprefix("sha256:")
        write_private(path=self._directory / "objects" / digest, payload=payload)
        write_private(path=self._pointer, payload=digest.encode())

    def load(self) -> Checkpoint | None:
        """Verify the complete object before restoring decisions or skipping any work."""
        if not self._pointer.exists():
            return None
        digest = self._pointer.read_text()
        if len(digest) != _SHA256_HEX_LENGTH or any(c not in "0123456789abcdef" for c in digest):
            raise InferenceError(message="Inspect the damaged graph checkpoint pointer.")
        payload = (self._directory / "objects" / digest).read_bytes()
        if hash_bytes(content=payload).value != f"sha256:{digest}":
            raise InferenceError(message="The graph checkpoint failed its integrity check.")
        return Checkpoint.model_validate_json(payload)
