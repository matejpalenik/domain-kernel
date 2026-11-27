from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope

from domain_kernel.discovery.application.contracts.inference_input import InferenceInput


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
