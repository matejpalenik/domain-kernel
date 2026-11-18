"""Detached inference requests and the caller-owned gateway boundary."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import ModelScope


@dataclass(frozen=True, kw_only=True)
class InferenceInput:
    """Untrusted source content with the exact issued citations."""

    text: str = field(repr=False)
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None:
        """Detach the evidence inventory and require explicit content."""
        require_text(value=self.text, field="Inference input")
        items = snapshot_sequence(items=self.evidence, item_type=Evidence, field="Evidence")
        if not items:
            raise ValueError("Supply an exact citation for inference input")
        object.__setattr__(self, "evidence", items)


@dataclass(frozen=True, kw_only=True)
class ModelRequest:
    """A bounded SDK request with separate instructions, context and source material."""

    instructions: str
    inputs: Sequence[InferenceInput] = field(repr=False)
    response_schema_json: str
    request_id: str
    timeout_seconds: float
    context_json: str | None = field(default=None, repr=False)
    scope: ModelScope | None = None

    def __post_init__(self) -> None:
        """Validate request identity and detach the inputs without interpreting source text."""
        require_text(value=self.instructions, field="Effective instructions")
        require_text(value=self.response_schema_json, field="Response schema")
        require_text(value=self.request_id, field="Request identity")
        if self.context_json is not None:
            require_text(value=self.context_json, field="Interpretation context")
        require_exact(value=self.timeout_seconds, expected=float, field="Timeout")
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Set a positive finite inference timeout")
        inputs = snapshot_sequence(items=self.inputs, item_type=InferenceInput, field="Inputs")
        if not inputs:
            raise ValueError("Select at least one verified inference input")
        object.__setattr__(self, "inputs", inputs)


@dataclass(frozen=True, kw_only=True)
class ModelResponse:
    """Provider output and usage detached from the transport."""

    output_json: str = field(repr=False)
    model_id: str
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_endpoint: str | None = None

    def __post_init__(self) -> None:
        """Verify metadata types while leaving response validation to the extractor."""
        require_text(value=self.output_json, field="Model output")
        require_text(value=self.model_id, field="Provider model")
        for value in (self.provider_request_id, self.provider_endpoint):
            if value is not None:
                require_text(value=value, field="Provider metadata")
        for value in (self.input_tokens, self.output_tokens):
            if value is not None:
                require_exact(value=value, expected=int, field="Token usage")
                if value < 0:
                    raise ValueError("Use nonnegative provider usage")


@dataclass(frozen=True, kw_only=True)
class TruncatedResponse:
    """A returned provider receipt with an incomplete output."""

    fragment: str | None = field(repr=False)
    model_id: str
    provider_request_id: str | None
    provider_endpoint: str
    input_tokens: int | None
    output_tokens: int | None


class TruncatedResponseError(InferenceError):
    """Carry the partial result privately to the response journal."""

    def __init__(self, *, response: TruncatedResponse) -> None:
        """Keep evidence of completion while giving the caller a safe diagnostic."""
        message = (
            "Inspect the incomplete provider response. "
            "Reduce the batch or increase its response limit."
        )
        super().__init__(
            message=message,
            issue=Issue(code="truncated_response", path=("response",), message=message),
        )
        self.response: TruncatedResponse = response


@runtime_checkable
class ModelGateway(Protocol, metaclass=ABCMeta):
    """A host-owned gateway that accepts the SDK's detached request."""

    @abstractmethod
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Run the asynchronously configured provider."""


@dataclass(frozen=True, kw_only=True)
class ExtractionSettings:
    """Captured inference settings belonging to one host client."""

    gateway: ModelGateway
    timeout_seconds: float
    max_attempts: int
    max_input_bytes: int
    max_output_bytes: int
    max_proposals: int
