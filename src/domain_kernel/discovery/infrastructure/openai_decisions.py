"""OpenAI Decisions transport for the built-in discovery workflow."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace
from importlib import import_module
from itertools import batched
from time import monotonic
from typing import TYPE_CHECKING, Protocol, final, override, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from domain_kernel._shared.application.inference import InferenceInput, ModelGateway, ModelResponse
from domain_kernel.discovery.application import endpoint_decisions, scope_shadow
from domain_kernel.discovery.infrastructure.litellm_gateway import (
    CLIENT_REQUEST_ID_HEADER,
    OPENAI_API_BASE,
    LiteLLMGateway,
)
from domain_kernel.shared.errors import InferenceError, MissingCapabilityError
from domain_kernel.shared.hashing import JsonValue, canonical_json_bytes, hash_bytes

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from contextlib import AbstractAsyncContextManager

    from domain_kernel._shared.application.inference import ModelRequest
    from domain_kernel.discovery.application.endpoint_decisions import Audit, Candidate
    from domain_kernel.discovery.infrastructure.local_replay import LocalReplayGateway
    from domain_kernel.sources.domain.models import SourceRevision


URL = f"{OPENAI_API_BASE}/decisions"
PROFILE = "/".join(
    (
        URL,
        endpoint_decisions.MODEL,
        endpoint_decisions.VERSION,
        endpoint_decisions.TEMPLATE,
        str(endpoint_decisions.THRESHOLD),
        scope_shadow.VERSION,
    )
)
_MAX_SECONDS = 5.0
_MAX_QUESTIONS = 16
_MAX_PACKET_BYTES = 16 * 1024
_SUCCESS = 200
_LOGGER = logging.getLogger(__name__)
_BODY = TypeAdapter(dict[str, JsonValue])
_OBJECT = TypeAdapter(dict[str, object])


def official_provider(gateways: Sequence[ModelGateway | None], /) -> LiteLLMGateway | None:
    """Use only the same official provider and credential throughout the workflow."""
    if not gateways or not isinstance(first := gateways[0], LiteLLMGateway):
        return None
    return (
        first
        if all(
            isinstance(gateway, LiteLLMGateway)
            and gateway.completion is None
            and gateway.api_base.rstrip("/") == OPENAI_API_BASE
            and (
                gateway.model.startswith("openai/")
                or (gateway.model.startswith("gpt-") and "/" not in gateway.model)
            )
            and gateway.api_key == first.api_key
            for gateway in gateways
        )
        else None
    )


class _HTTPResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    def json(self) -> object: ...


class _HTTPClient(Protocol):
    async def post(
        self, url: str, /, *, content: bytes, headers: dict[str, str]
    ) -> _HTTPResponse: ...


@runtime_checkable
class _HTTP(Protocol):
    TimeoutException: type[Exception]

    def AsyncClient(  # noqa: N802 - Vendor constructor.
        self, *, timeout: float, follow_redirects: bool, trust_env: bool
    ) -> AbstractAsyncContextManager[_HTTPClient]: ...


async def post(
    *, body: JsonValue, api_key: str, timeout_seconds: float, client_request_id: str
) -> tuple[object, str | None]:
    """Send exactly the tested request to the official API, without retries or redirects."""
    try:
        api = import_module("httpx")
    except ImportError:
        raise MissingCapabilityError(message="Install the Domain Kernel inference extra.") from None
    if not isinstance(api, _HTTP):
        raise MissingCapabilityError(message="Use an asynchronous HTTP transport.")
    try:
        async with api.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False
        ) as client:
            response = await client.post(
                URL,
                content=canonical_json_bytes(value=body),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    CLIENT_REQUEST_ID_HEADER: client_request_id,
                },
            )
            if response.status_code != _SUCCESS:
                raise InferenceError(
                    message="The OpenAI Decisions service did not return a success."
                )
            return response.json(), response.headers.get("x-request-id")
    except api.TimeoutException:
        raise TimeoutError from None


class _ProviderReply(BaseModel, strict=True):
    answers: list[JsonValue]


class _Usage(BaseModel, strict=True):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


def _usage(raw: object, /) -> _Usage:
    try:
        return _Usage.model_validate(raw)
    except ValidationError:
        return _Usage()


@final
@dataclass(frozen=True, kw_only=True)
class Gateway(ModelGateway):
    """Adapt the private gate packet to a detached replay receipt."""

    api_key: str = field(repr=False)

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        payload = _BODY.validate_json(request.context_json or "{}")
        started = monotonic()
        request_id = uuid4().hex
        upstream = None
        usage = _Usage()
        _LOGGER.info("Dispatching Decisions request %s", request_id)
        try:
            async with asyncio.timeout(request.timeout_seconds):
                raw, upstream = await post(
                    body=payload,
                    api_key=self.api_key,
                    timeout_seconds=request.timeout_seconds,
                    client_request_id=request_id,
                )
            item = _OBJECT.validate_python(raw)
            usage = _usage(item.get("usage"))
            answers = _ProviderReply.model_validate(item).answers
            reply = endpoint_decisions.Reply(
                status="ok", seconds=monotonic() - started, answers=answers
            )
        except TimeoutError:
            reply = endpoint_decisions.Reply(status="timeout", seconds=monotonic() - started)
        except (ValidationError, ValueError, TypeError):
            reply = endpoint_decisions.Reply(status="malformed", seconds=monotonic() - started)
        except Exception:  # noqa: BLE001 - Transport failures can include provider text and credentials.
            reply = endpoint_decisions.Reply(status="unavailable", seconds=monotonic() - started)
        return ModelResponse(
            output_json=reply.model_dump_json(),
            model_id=endpoint_decisions.MODEL,
            provider_endpoint=URL,
            provider_request_id=upstream or request_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )


@dataclass(frozen=True, kw_only=True)
class Gate:
    """Run bounded classification while reserving the rest of the deadline for fallback."""

    journal: LocalReplayGateway
    slots: asyncio.Semaphore
    max_request_bytes: int
    stage_timeout_seconds: float

    async def route(
        self,
        *,
        request: ModelRequest,
        audit: Audit,
        candidates: Sequence[Candidate],
        started: float,
    ) -> set[str]:
        """Return IDs with sufficient Decisions support and retain the reason for every route."""
        remaining = request.timeout_seconds - (monotonic() - started)
        deadline = monotonic() + min(
            _MAX_SECONDS, self.stage_timeout_seconds, request.timeout_seconds / 10, remaining / 4
        )
        outcomes: dict[str, tuple[str, float | None]] = {}
        for group in _same_revision(candidates=candidates):
            ids = tuple(c.claim.claim_id for c in group)
            packet = canonical_json_bytes(value=endpoint_decisions.body(group))
            if len(packet) > min(self.max_request_bytes, _MAX_PACKET_BYTES):
                outcomes.update(dict.fromkeys(ids, ("packet_limit", None)))
                continue
            if deadline <= monotonic():
                outcomes.update(dict.fromkeys(ids, ("gate_deadline", None)))
                continue
            outcomes.update(
                await self._classify(
                    audit=audit,
                    pending=replace(
                        request,
                        instructions=PROFILE,
                        context_json=packet.decode(),
                        response_schema_json=json.dumps(
                            endpoint_decisions.Reply.model_json_schema()
                        ),
                        inputs=tuple(
                            InferenceInput(text=c.quote, evidence=c.passage.evidence) for c in group
                        ),
                        max_output_tokens=None,
                        use_provider_output_limit=False,
                        retry_cancelled=True,
                    ),
                    ids=ids,
                    digest=hash_bytes(content=packet).value,
                    deadline=deadline,
                )
            )
        bypassed: set[str] = set()
        for item in audit.routes:
            if decision := outcomes.get(item.claim_id):
                item.reason, item.support = decision
                if item.reason == "supported":
                    bypassed.add(item.claim_id)
        return bypassed

    async def _classify(
        self,
        *,
        audit: Audit,
        pending: ModelRequest,
        ids: tuple[str, ...],
        digest: str,
        deadline: float,
    ) -> dict[str, tuple[str, float | None]]:
        response = None
        try:
            async with asyncio.timeout_at(
                asyncio.get_running_loop().time() + deadline - monotonic()
            ):
                async with self.slots:
                    response = await self.journal.generate(
                        request=replace(
                            pending, timeout_seconds=max(0.001, deadline - monotonic() - 0.02)
                        )
                    )
            reply = endpoint_decisions.Reply.model_validate_json(response.output_json)
        except TimeoutError:
            reply = endpoint_decisions.Reply(status="timeout", seconds=0)
        except ValidationError:
            reply = endpoint_decisions.Reply(status="malformed", seconds=0)
        except (InferenceError, OSError):
            reply = endpoint_decisions.Reply(status="unavailable", seconds=0)
        audit.calls.append(
            endpoint_decisions.CallReceipt(
                request_digest=digest,
                claim_ids=ids,
                status=reply.status,
                seconds=reply.seconds if response is not None else None,
                provider_request_id=None if response is None else response.provider_request_id,
                input_tokens=None if response is None else response.input_tokens,
                output_tokens=None if response is None else response.output_tokens,
            )
        )
        return endpoint_decisions.outcomes(reply=reply, ids=ids)


def _same_revision(*, candidates: Sequence[Candidate]) -> Iterator[tuple[Candidate, ...]]:
    groups: dict[SourceRevision, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.passage.evidence[0].source].append(candidate)
    for group in groups.values():
        yield from batched(group, _MAX_QUESTIONS, strict=False)
