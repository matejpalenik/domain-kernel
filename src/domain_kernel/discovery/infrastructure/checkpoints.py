"""Private content-addressed state objects and atomic, run-scoped graph checkpoints."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import final

from pydantic import BaseModel, Field

from domain_kernel.discovery.application.claim_extraction import (  # noqa: TC001 -- Pydantic resolves runtime schemas
    Alias,
    Anchor,
    BatchResult,
    Finding,
    VerifiedAlias,
)
from domain_kernel.discovery.application.endpoint_decisions import Audit as DecisionsAudit  # noqa: TC001 -- Pydantic schema
from domain_kernel.discovery.application.errors.inference_error import InferenceError
from domain_kernel.discovery.application.focused_omissions import FollowUp  # noqa: TC001 -- Pydantic schema
from domain_kernel.discovery.application.held_endpoints import Recovery
from domain_kernel.discovery.application.omission_windows import WindowReceipt  # noqa: TC001 -- Pydantic schema
from domain_kernel.shared.hashing import Hashing

_SHA256_HEX_LENGTH = 64


class Receipt(BaseModel):
    """Provider metadata retained independently of untrusted response content."""

    model_id: str
    provider_endpoint: str | None
    input_tokens: int | None
    output_tokens: int | None
    stage: str | None = None
    profile: str | None = None


class Checkpoint(BaseModel):
    """An immutable stage snapshot referenced by the run's small completion pointer."""

    stage: str
    batches: list[BatchResult]
    aliases: dict[str, Alias | VerifiedAlias]
    edge_findings: dict[str, Finding]
    receipts: list[Receipt]
    endpoint_evidence: dict[str, list[Anchor]] = Field(default_factory=dict)
    held_recovery: Recovery = Field(default_factory=Recovery)
    omission_windows: list[WindowReceipt] = Field(default_factory=list)
    focused_omissions: list[FollowUp] = Field(default_factory=list)
    endpoint_decisions: DecisionsAudit | None = None


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
        digest = Hashing.hash_bytes(content=payload).value.removeprefix("sha256:")
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
        if Hashing.hash_bytes(content=payload).value != f"sha256:{digest}":
            raise InferenceError(message="The graph checkpoint failed its integrity check.")
        return Checkpoint.model_validate_json(payload)
