"""Optional asynchronous LiteLLM gateway for configured OpenAI-compatible endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import import_module
from typing import (
    TYPE_CHECKING,
    ClassVar,
    NotRequired,
    Protocol,
    TypedDict,
    Unpack,
    final,
    override,
    runtime_checkable,
)
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from domain_kernel.shared.application.inference import (
    InferenceTimeoutError,
    ModelGateway,
    ModelResponse,
    TruncatedResponse,
    TruncatedResponseError,
)
from domain_kernel.shared.domain.record_encoding import record_value
from domain_kernel.shared.errors import InferenceError, MissingCapabilityError
from domain_kernel.shared.hashing import JsonValue, canonical_json_bytes
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.shared.application.inference import ModelRequest


OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
CLIENT_REQUEST_ID_HEADER = "X-Client-Request-Id"
_LOGGER = logging.getLogger(__name__)
_CHAT_FRAMING_BYTES = 2048
_RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
_TIMEOUT_STATUSES = frozenset({408, 504})
_JSON_OBJECT = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue])


class _Call(TypedDict):
    model: str
    api_base: str
    api_key: str
    messages: list[dict[str, str]]
    response_format: dict[str, JsonValue]
    timeout: float
    max_completion_tokens: NotRequired[int]
    num_retries: int
    max_retries: int
    extra_headers: dict[str, str]
    reasoning_effort: NotRequired[str]


class CompletionTransport(Protocol):
    """The limited async completion interface used by this adapter."""

    async def __call__(self, **kwargs: Unpack[_Call]) -> object:
        """Send one provider completion request."""
        ...


@runtime_checkable
class _LiteLLM(Protocol):
    async def acompletion(self, **kwargs: Unpack[_Call]) -> object: ...


class _TransportRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore",
        strict=True,
        hide_input_in_errors=True,
    )


class _Message(_TransportRecord):
    content: str | None = None


class _Choice(_TransportRecord):
    message: _Message
    finish_reason: str | None = None


class _PromptTokens(_TransportRecord):
    cached_tokens: int | None = None
    cache_write_tokens: int | None = None


class _CompletionTokens(_TransportRecord):
    reasoning_tokens: int | None = None


class _Usage(_TransportRecord):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tokens_details: _PromptTokens | None = None
    completion_tokens_details: _CompletionTokens | None = None


class _Completion(_TransportRecord):
    id: str | None = None
    model: str
    choices: list[_Choice]
    usage: _Usage | None = None


@runtime_checkable
class _HttpFailure(Protocol):
    @property
    def status_code(self) -> int: ...


def _completion() -> CompletionTransport:
    try:
        provider = import_module(name="litellm")
    except ImportError:
        raise MissingCapabilityError(message="Install the Domain Kernel inference extra.") from None
    if not isinstance(provider, _LiteLLM):
        raise MissingCapabilityError(message="Use an installed LiteLLM SDK with acompletion.")
    return provider.acompletion


def _messages(*, request: ModelRequest) -> list[dict[str, str]]:
    next_citation = 1
    sections: list[JsonValue] = []
    for item in request.inputs:
        cited: list[JsonValue] = []
        for evidence in item.evidence:
            cited.append(
                {
                    "citation": next_citation,
                    "source_digest": evidence.source.revision_id.value,
                    "locator": record_value(value=evidence.locator),
                }
            )
            next_citation += 1
        sections.append({"text": item.text, "citations": tuple(cited)})
    payload = canonical_json_bytes(
        value={
            "interpretation_context": (
                None
                if request.context_json is None
                else _JSON_OBJECT.validate_json(request.context_json)
            ),
            "verified_source_material": tuple(sections),
        }
    ).decode()
    return [
        {"role": "system", "content": request.instructions},
        {"role": "user", "content": payload},
    ]


def _released_response(
    *,
    raw: object,
    endpoint: str,
    stage: str | None,
    client_request_id: str,
) -> ModelResponse:
    # LiteLLM exposes some transport fields through Pydantic extras.
    # Normalize those fields before applying the SDK's detached contract.
    completion = _Completion.model_validate(
        raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw,
    )
    if len(completion.choices) != 1:
        raise InferenceError(message="Inspect the provider completion result.")
    choice = completion.choices[0]
    content = choice.message.content
    usage = completion.usage
    if stage is not None and usage is not None:
        prefix = "Inference usage stage=%s request=%s stop=%s input=%s output=%s"
        message = f"{prefix} reasoning=%s cache_read=%s cache_write=%s"
        _LOGGER.info(
            message,
            stage,
            client_request_id,
            choice.finish_reason,
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.completion_tokens_details.reasoning_tokens
            if usage.completion_tokens_details
            else None,
            usage.prompt_tokens_details.cached_tokens if usage.prompt_tokens_details else None,
            usage.prompt_tokens_details.cache_write_tokens if usage.prompt_tokens_details else None,
        )
    if choice.finish_reason == "length":
        raise TruncatedResponseError(
            response=TruncatedResponse(
                fragment=content,
                model_id=completion.model,
                provider_request_id=completion.id,
                provider_endpoint=endpoint,
                input_tokens=None if usage is None else usage.prompt_tokens,
                output_tokens=None if usage is None else usage.completion_tokens,
            ),
        )
    if choice.finish_reason != "stop" or content is None:
        raise InferenceError(message="Inspect the incomplete provider response.")
    return ModelResponse(
        output_json=content,
        model_id=completion.model,
        provider_request_id=completion.id,
        input_tokens=None if usage is None else usage.prompt_tokens,
        output_tokens=None if usage is None else usage.completion_tokens,
        provider_endpoint=endpoint,
    )


@final
@dataclass(frozen=True, kw_only=True)
class LiteLLMGateway(ModelGateway):
    """Route structured requests to the explicitly selected compatible provider."""

    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    api_base: str = OPENAI_API_BASE
    reasoning_effort: str | None = "none"
    max_output_tokens: int = 2048
    completion: CompletionTransport | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the explicit endpoint and bounded response configuration."""
        TextValidation.require_text(value=self.api_key, field="Endpoint API key")
        TextValidation.require_text(value=self.model, field="Provider model")
        TextValidation.require_text(value=self.api_base, field="Provider API base")
        if self.reasoning_effort is not None:
            TextValidation.require_text(value=self.reasoning_effort, field="Reasoning effort")
        endpoint = urlsplit(self.api_base)
        if (
            endpoint.scheme not in {"http", "https"}
            or endpoint.hostname is None
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("Supply an HTTP API base without credentials, query or fragment")
        RuntimeTypeValidation.require_exact(
            value=self.max_output_tokens, expected=int, field="Maximum output tokens"
        )
        if self.max_output_tokens < 1:
            raise ValueError("Set a positive model response token limit")

    @property
    def supports_schema_discovery(self) -> bool:
        """Accept the SDK's structured schema discovery requests."""
        return True

    def input_ceiling(self, *, request: ModelRequest) -> int:
        """Conservatively bound text tokens from UTF-8 bytes and chat framing."""
        framed_messages = sum(len(item["content"].encode()) for item in _messages(request=request))
        return framed_messages + len(request.response_schema_json.encode()) + _CHAT_FRAMING_BYTES

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Send one asynchronous request using only the configured endpoint and key."""
        try:
            schema = _JSON_OBJECT.validate_json(request.response_schema_json)
            messages = _messages(request=request)
        except ValidationError:
            raise InferenceError(
                message="Supply the exact SDK response schema and context."
            ) from None
        client_request_id = uuid4().hex
        kwargs: _Call = {
            "model": self.model,
            "api_base": self.api_base,
            "api_key": self.api_key,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "domain_kernel_proposals",
                    "strict": True,
                    "schema": schema,
                },
            },
            "timeout": request.timeout_seconds,
            "num_retries": 0,
            "max_retries": 0,
            "extra_headers": {CLIENT_REQUEST_ID_HEADER: client_request_id},
        }
        if not request.use_provider_output_limit:
            kwargs["max_completion_tokens"] = min(
                self.max_output_tokens, request.max_output_tokens or self.max_output_tokens
            )
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort
        transport = _completion() if self.completion is None else self.completion
        _LOGGER.info(
            "Dispatching inference request %s stage=%s", client_request_id, request.provider_stage
        )
        try:
            raw = await transport(**kwargs)
        except Exception as error:  # noqa: BLE001 - Provider exceptions can include request secrets.
            status = error.status_code if isinstance(error, _HttpFailure) else None
            if isinstance(error, TimeoutError) or status in _TIMEOUT_STATUSES:
                _LOGGER.warning("Inference request %s timed out", client_request_id)
                raise InferenceTimeoutError(timeout_seconds=request.timeout_seconds) from None
            raise InferenceError(
                message="Check the configured LiteLLM endpoint, model and credentials.",
                retryable=isinstance(error, OSError) or status in _RETRY_STATUSES,
            ) from None
        try:
            return _released_response(
                raw=raw,
                endpoint=self.api_base,
                stage=request.provider_stage,
                client_request_id=client_request_id,
            )
        except (TypeError, ValueError):
            raise InferenceError(message="Inspect the provider completion metadata.") from None
