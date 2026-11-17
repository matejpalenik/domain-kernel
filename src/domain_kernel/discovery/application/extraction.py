"""Extract typed proposals with a captured prompt, exact evidence and guarded replay."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel._shared.application.inference import InferenceInput, ModelRequest, ModelResponse
from domain_kernel._shared.application.persistence import (
    Invocation,
    OperationOutcome,
    keep_work_leased,
)
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.discovery.application.ports import ExtractionTransaction
from domain_kernel.discovery.application.prompts import capture_prompt
from domain_kernel.discovery.application.structured_output import decode_proposals, response_schema
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.models import (
    DiscoveryDraft,
    DiscoveryProgress,
    ExtractionIntent,
    ExtractionProvenance,
    RunStatus,
)
from domain_kernel.shared.errors import (
    InferenceError,
    MissingCapabilityError,
    ResourceLimitError,
    ScopeMismatchError,
    StaleStateError,
)
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.models import SourceRevision

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from domain_kernel._shared.application.catalogs import CatalogTransaction
    from domain_kernel._shared.application.inference import ExtractionSettings
    from domain_kernel._shared.application.persistence import Lease, UnitOfWorkFactory
    from domain_kernel.discovery.domain.models import (
        DiscoveryPrompt,
        InterpretationContext,
        ProgressCallback,
    )
    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.sources.application.service import Sources


_LEASE_RENEW_INTERVAL = 20


@dataclass(kw_only=True)
class _LeasedExtraction:
    invocation: Invocation
    lease: Lease


@dataclass(frozen=True, kw_only=True)
class ExtractionRequest:
    """An exact interpretation request retained before provider execution."""

    context: InterpretationContext
    revisions: tuple[SourceRevision, ...]
    prompt: DiscoveryPrompt
    schema: str
    callback: ProgressCallback | None
    run_id: DiscoveryRunId | None = None


@final
class Extraction:
    """Read exact evidence and persist an immutable draft before returning it."""

    def __init__(
        self,
        *,
        settings: ExtractionSettings,
        sources: Sources,
        resources: UnitOfWorkFactory[CatalogTransaction],
    ) -> None:
        """Bind the original client's gateway and repositories."""
        self._settings = settings
        self._sources = sources
        self._resources = resources

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[ExtractionTransaction]:
        async with self._resources() as transaction:
            if not isinstance(transaction, ExtractionTransaction):
                raise MissingCapabilityError(message="Configure durable extraction persistence.")
            async with transaction.begin():
                yield transaction

    async def extract(  # noqa: PLR0913 - Explicit extraction identity and instruction controls.
        self,
        *,
        actor: str,
        context: InterpretationContext,
        source_revisions: Sequence[SourceRevision],
        additional_instructions: str | None,
        prompt_override: str | None,
        idempotency_key: str | None,
        on_progress: ProgressCallback | None,
    ) -> DiscoveryDraft:
        """Return a validated result or a stored replay for the same requested extraction."""
        require_text(value=actor, field="Actor")
        revisions = snapshot_sequence(
            items=source_revisions,
            item_type=SourceRevision,
            field="Source revisions",
        )
        if not revisions or len(set(revisions)) != len(revisions):
            raise ValueError("Select distinct exact source revisions")
        if any(item.project_id != context.scope.project_id for item in revisions):
            raise ScopeMismatchError
        schema = response_schema()
        prompt = capture_prompt(
            additional_instructions=additional_instructions,
            prompt_override=prompt_override,
            schema_json=schema,
        )
        return await self.extract_captured(
            actor=actor,
            idempotency_key=idempotency_key,
            request=ExtractionRequest(
                context=context,
                revisions=revisions,
                prompt=prompt,
                schema=schema,
                callback=on_progress,
            ),
        )

    async def extract_captured(
        self,
        *,
        actor: str,
        idempotency_key: str | None,
        request: ExtractionRequest,
    ) -> DiscoveryDraft:
        """Recover or execute a request with its original schema, prompt and context."""
        context = request.context
        invocation = Invocation.resolve(
            project_id=context.scope.project_id,
            model_id=context.scope.model_id,
            operation="extract_proposals",
            actor=actor,
            key=idempotency_key,
            intent=record_value(
                value=(
                    request.revisions,
                    request.prompt.additional_instructions,
                    request.prompt.prompt_override,
                )
            ),
        )
        async with self._transaction() as transaction:
            lease = await transaction.operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(lease, OperationOutcome):
                if lease.resource_kind != "discovery_draft":
                    raise StaleStateError(message="Inspect the stored extraction outcome.")
                return await transaction.extraction.draft(
                    identifier=DiscoveryDraftId(value=lease.resource_id),
                    scope=context.scope,
                )
        leased = _LeasedExtraction(invocation=invocation, lease=lease)
        try:
            draft = await self._with_lease(request=request, leased=leased)
            async with self._transaction() as transaction:
                await transaction.extraction.complete(draft=draft)
                await transaction.operations.complete(
                    invocation=invocation,
                    lease=leased.lease,
                    outcome=OperationOutcome(
                        resource_kind="discovery_draft", resource_id=draft.id.value
                    ),
                )
        except BaseException:
            with suppress(StaleStateError):
                async with self._transaction() as transaction:
                    await transaction.operations.release(invocation=invocation, lease=leased.lease)
            raise
        if request.callback is not None:
            request.callback(
                DiscoveryProgress(
                    scope=context.scope,
                    run_id=draft.run_id,
                    stage=RunStatus.NEEDS_REVIEW,
                    completed=len(request.revisions),
                    total=len(request.revisions),
                )
            )
        return draft

    async def _with_lease(
        self,
        *,
        request: ExtractionRequest,
        leased: _LeasedExtraction,
    ) -> DiscoveryDraft:
        async def renew() -> None:
            async with self._transaction() as transaction:
                updated = await transaction.operations.renew(
                    invocation=leased.invocation, lease=leased.lease
                )
            leased.lease = updated

        return await keep_work_leased(
            work=self._execute(request=request), renew=renew, interval=_LEASE_RENEW_INTERVAL
        )

    async def _inputs(self, *, revisions: Sequence[SourceRevision]) -> tuple[InferenceInput, ...]:
        inputs: list[InferenceInput] = []
        remaining = self._settings.max_input_bytes
        for revision in revisions:
            citations = await self._sources.citations(revision=revision)
            if not citations:
                raise EvidenceUnavailableError
            for citation in citations:
                evidence = await self._sources.get_evidence(evidence=citation)
                remaining -= len(evidence.excerpt.encode())
                if remaining < 0:
                    raise ResourceLimitError(
                        message="Select a corpus within the inference input budget."
                    )
                inputs.append(InferenceInput(text=evidence.excerpt, evidence=(citation,)))
        return tuple(inputs)

    async def _execute(self, *, request: ExtractionRequest) -> DiscoveryDraft:
        context = request.context
        inputs = await self._inputs(revisions=request.revisions)
        corpus = tuple(citation for item in inputs for citation in item.evidence)
        fingerprint = hash_json(value=record_value(value=(request.prompt, context, corpus))).value
        intent = ExtractionIntent(
            id=DiscoveryDraftId(value=uuid4().hex),
            run_id=request.run_id or DiscoveryRunId(value=uuid4().hex),
            context=context,
            source_revisions=request.revisions,
            prompt=request.prompt,
            processing_fingerprint=fingerprint,
        )
        approved: tuple[JsonValue, ...] = tuple(
            {"name": item.name, "meaning": item.meaning} for item in context.approved_definitions
        )
        context_json = canonical_json_bytes(
            value={"description": context.model_description, "approved_meanings": approved},
        ).decode()
        policy = self._settings
        if (
            len(context_json.encode()) + sum(len(item.text.encode()) for item in inputs)
            > policy.max_input_bytes
        ):
            raise ResourceLimitError(
                message="Keep the interpretation context and corpus within the input budget."
            )
        async with self._transaction() as transaction:
            await transaction.extraction.reserve(intent=intent)
        if request.callback is not None:
            request.callback(
                DiscoveryProgress(
                    scope=context.scope,
                    run_id=intent.run_id,
                    stage=RunStatus.EXTRACTING,
                    completed=0,
                    total=len(request.revisions),
                )
            )
        response = await self._generate(
            request=ModelRequest(
                instructions=request.prompt.effective_instructions,
                inputs=inputs,
                response_schema_json=request.schema,
                request_id=intent.run_id.value,
                timeout_seconds=policy.timeout_seconds,
                context_json=context_json,
            ),
        )
        if len(response.output_json.encode()) > policy.max_output_bytes:
            raise InferenceError(
                message="Keep the provider output within the configured byte budget."
            )
        provenance = ExtractionProvenance(
            processing_fingerprint=fingerprint,
            extractor_id="domain-kernel/structured-extractor",
            extractor_version=request.prompt.response_schema_version,
            provider_model_id=response.model_id,
            provider_endpoint=response.provider_endpoint,
            provider_request_id=response.provider_request_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        proposals = decode_proposals(
            output=response.output_json,
            context=context,
            corpus=corpus,
            provenance=provenance,
            max_proposals=policy.max_proposals,
        )
        return DiscoveryDraft(
            id=intent.id,
            scope=context.scope,
            run_id=intent.run_id,
            context=context,
            source_revisions=request.revisions,
            proposals=proposals,
            prompt=request.prompt,
            processing_fingerprint=fingerprint,
            provenance=provenance,
        )

    async def _generate(self, *, request: ModelRequest) -> ModelResponse:
        attempts = self._settings.max_attempts
        for step in range(attempts):
            try:
                return await self._attempt(request=request)
            except InferenceError as error:
                if not error.retryable or step + 1 == attempts:
                    raise
        raise AssertionError("Inference policy must allow at least one attempt")

    async def _attempt(self, *, request: ModelRequest) -> ModelResponse:
        try:
            async with asyncio.timeout(delay=request.timeout_seconds):
                response = await self._settings.gateway.generate(request=request)
            require_exact(value=response, expected=ModelResponse, field="Provider response")
        except TimeoutError:
            raise InferenceError(
                message="The inference provider timed out.", retryable=True
            ) from None
        except OSError:
            raise InferenceError(
                message="Check access to the inference provider.", retryable=True
            ) from None
        except (TypeError, ValueError, RuntimeError):
            raise InferenceError(
                message="Check the inference provider configuration and response."
            ) from None
        return response
