"""Detached inference requests and the caller-owned gateway boundary."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import InferenceError
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import ModelScope


@dataclass(frozen=True, kw_only=True)
class InferenceInput:
    """Untrusted source content with the exact issued citations."""

    text: str = field(repr=False)
    evidence: Sequence[Evidence]
    is_table: bool = False

    def __post_init__(self) -> None:
        """Detach the evidence inventory and require explicit content."""
        TextValidation.require_text(value=self.text, field="Inference input")
        RuntimeTypeValidation.require_exact(value=self.is_table, expected=bool, field="Table input")
        items = SequenceValidation.snapshot_sequence(
            items=self.evidence, item_type=Evidence, field="Evidence"
        )
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
    approved_concept_pins: tuple[tuple[str, str, int], ...] = field(default=(), repr=False)
    approved_concept_aliases: tuple[tuple[str, tuple[str, ...]], ...] = field(
        default=(), repr=False
    )
    max_output_tokens: int | None = None
    use_provider_output_limit: bool = False
    discovery_output_bytes: int | None = None
    discovery_continuation: tuple[tuple[int, int, int], ...] = ()
    discovery_pending_concepts: tuple[tuple[str, str, str], ...] = ()
    retry_cancelled: bool = False
    provider_stage: str | None = None

    def __post_init__(self) -> None:
        """Validate request identity and detach the inputs without interpreting source text."""
        TextValidation.require_text(value=self.instructions, field="Effective instructions")
        TextValidation.require_text(value=self.response_schema_json, field="Response schema")
        TextValidation.require_text(value=self.request_id, field="Request identity")
        if self.context_json is not None:
            TextValidation.require_text(value=self.context_json, field="Interpretation context")
        if self.provider_stage is not None:
            TextValidation.require_text(value=self.provider_stage, field="Provider stage")
        RuntimeTypeValidation.require_exact(
            value=self.timeout_seconds, expected=float, field="Timeout"
        )
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Set a positive finite inference timeout")
        RuntimeTypeValidation.require_exact(
            value=self.use_provider_output_limit, expected=bool, field="Provider limit"
        )
        if self.max_output_tokens is not None:
            if self.use_provider_output_limit:
                raise ValueError("Choose either an SDK output ceiling or the provider limit")
            RuntimeTypeValidation.require_exact(
                value=self.max_output_tokens, expected=int, field="Maximum output tokens"
            )
            if self.max_output_tokens <= 0:
                raise ValueError("Set a positive output token limit")
        if self.discovery_output_bytes is not None:
            RuntimeTypeValidation.require_exact(
                value=self.discovery_output_bytes, expected=int, field="Discovery bytes"
            )
            if self.discovery_output_bytes <= 0:
                raise ValueError("Set a positive discovery output limit")
        inputs = SequenceValidation.snapshot_sequence(
            items=self.inputs, item_type=InferenceInput, field="Inputs"
        )
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
    discovery_binding_json: str | None = field(default=None, repr=False)
    discovery_held_json: str | None = field(default=None, repr=False)
    discovery_coverage_json: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Verify metadata types while leaving response validation to the extractor."""
        TextValidation.require_text(value=self.output_json, field="Model output")
        TextValidation.require_text(value=self.model_id, field="Provider model")
        if self.discovery_binding_json is not None:
            TextValidation.require_text(
                value=self.discovery_binding_json, field="Discovery binding"
            )
        if self.discovery_held_json is not None:
            TextValidation.require_text(
                value=self.discovery_held_json, field="Held discovery relationships"
            )
        if self.discovery_coverage_json is not None:
            TextValidation.require_text(
                value=self.discovery_coverage_json, field="Discovery coverage"
            )
        for value in (self.provider_request_id, self.provider_endpoint):
            if value is not None:
                TextValidation.require_text(value=value, field="Provider metadata")
        for value in (self.input_tokens, self.output_tokens):
            if value is not None:
                RuntimeTypeValidation.require_exact(value=value, expected=int, field="Token usage")
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


class InferenceTimeoutError(InferenceError):
    """An inference request reached its deadline before returning a response."""

    def __init__(self, *, timeout_seconds: float) -> None:
        """Retain the configured deadline for replay and diagnostics."""
        message = (
            "The inference request timed out. "
            f"The configured request limit is {timeout_seconds:g} seconds."
        )
        super().__init__(
            message=message,
            retryable=True,
            issue=Issue(code="provider_timeout", path=("response",), message=message),
        )
        self.timeout_seconds: float = timeout_seconds


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
    explicit_limits: frozenset[str] = frozenset()
