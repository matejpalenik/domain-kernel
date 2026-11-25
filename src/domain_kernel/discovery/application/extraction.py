"""Extract typed proposals with a captured prompt, exact evidence and guarded replay."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, final
from uuid import uuid4

from pydantic import TypeAdapter

from domain_kernel.discovery.application import (
    continuation,
    omission_windows,
    schema_mapping,
)
from domain_kernel.discovery.application.ports import (
    BatchedProposalGateway,
    BindingContractGateway,
    DiscoveryStageLimits,
    ExtractionTransaction,
    ProfiledDiscoveryGateway,
    SchemaDiscoveryGateway,
)
from domain_kernel.discovery.application.prompts import capture_prompt
from domain_kernel.discovery.application.schema_compact import CompactDiscovery
from domain_kernel.discovery.application.structured_output import (
    BoundProposalInput,
    decode_bound_proposals,
    decode_held_relationships,
    decode_proposals,
    response_schema,
)
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.models import (
    DiscoveryDraft,
    DiscoveryProgress,
    ExtractionIntent,
    ExtractionProvenance,
    RunStatus,
)
from domain_kernel.discovery.domain.schema_policy import (
    COMPACT_STAGES,
    DISCOVERY_MAX_OUTPUT_BYTES,
    DISCOVERY_MAX_PROPOSALS,
    DISCOVERY_STAGE_ATTEMPTS,
    DISCOVERY_STAGE_TIMEOUT_SECONDS,
    DISCOVERY_TIMEOUT_SECONDS,
    SCHEMA_V23,
)
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.shared.application.inference import InferenceInput, ModelRequest, ModelResponse
from domain_kernel.shared.application.persistence import (
    Invocation,
    OperationOutcome,
    keep_work_leased,
)
from domain_kernel.shared.domain.codecs.record_encoding import record_value
from domain_kernel.shared.errors import (
    InferenceError,
    MissingCapabilityError,
    ResourceLimitError,
    ScopeMismatchError,
    StaleStateError,
)
from domain_kernel.shared.hashing import canonical_json_bytes, hash_json
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.models import SourceRevision
from domain_kernel.sources.domain.parsed import ParsedTable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from domain_kernel.discovery.domain.coverage import DiscoveryCoverage
    from domain_kernel.discovery.domain.models import (
        DiscoveryPrompt,
        InterpretationContext,
        ProgressCallback,
    )
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.application.catalogs import CatalogTransaction
    from domain_kernel.shared.application.inference import ExtractionSettings
    from domain_kernel.shared.application.persistence import Lease, UnitOfWorkFactory
    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.sources.application.service import Sources
    from domain_kernel.sources.domain.models import Evidence


_LEASE_RENEW_INTERVAL = 20
_SCHEMA_FRAME = TypeAdapter(dict[str, object])


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
    ancestry: tuple[DiscoveryDraft, ...] = ()
    schema_version: str | None = None
    schema_sources: tuple[DiscoveryDraft, ...] | None = None
    schema_prior: DiscoveryDraft | None = None


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

    def for_discovery(self) -> Extraction:
        """Apply v23 limits only to the coordinated workflow, not standalone extraction."""
        limits = self._settings
        explicit = limits.explicit_limits
        return Extraction(
            settings=replace(
                limits,
                timeout_seconds=limits.timeout_seconds
                if "timeout_seconds" in explicit
                else DISCOVERY_TIMEOUT_SECONDS,
                max_attempts=limits.max_attempts if "max_attempts" in explicit else 1,
                max_proposals=limits.max_proposals
                if "max_proposals" in explicit
                else DISCOVERY_MAX_PROPOSALS,
                max_output_bytes=limits.max_output_bytes
                if "max_output_bytes" in explicit
                else DISCOVERY_MAX_OUTPUT_BYTES,
            ),
            sources=self._sources,
            resources=self._resources,
        )

    def require_discovery(self) -> None:
        """Reject gateways that cannot accept structured discovery requests."""
        gateway = self._settings.gateway
        if not isinstance(gateway, SchemaDiscoveryGateway) or not gateway.supports_schema_discovery:
            raise MissingCapabilityError(
                message="Configure a gateway that supports structured schema discovery."
            )

    @property
    def workflow_profile(self) -> str | None:
        """Read the execution profile of the configured staged gateway."""
        gateway = self._settings.gateway
        return gateway.discovery_profile if isinstance(gateway, ProfiledDiscoveryGateway) else None

    @property
    def _proposal_batch_size(self) -> int | None:
        gateway = self._settings.gateway
        if isinstance(gateway, BatchedProposalGateway) and gateway.batch_proposals:
            return self._settings.max_proposals
        return None

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
        TextValidation.require_text(value=actor, field="Actor")
        revisions = SequenceValidation.snapshot_sequence(
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
                    *((request.schema_version,) if request.schema_version is not None else ()),
                    *(
                        (tuple(item.id for item in request.schema_sources),)
                        if request.schema_sources is not None
                        else ()
                    ),
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
                batch_size = (
                    self._proposal_batch_size
                    if not (draft.relationship_bindings or draft.schema_mappings)
                    else None
                )
                if batch_size is None:
                    await transaction.extraction.complete(draft=draft)
                else:
                    await transaction.extraction.complete(draft=draft, batch_size=batch_size)
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

    async def _inputs(
        self, *, revisions: Sequence[SourceRevision], parent: DiscoveryDraft | None = None
    ) -> tuple[InferenceInput, ...]:
        inputs: list[InferenceInput] = []
        remaining = self._settings.max_input_bytes
        for revision in revisions:
            start = len(inputs)
            pinned = (
                tuple(
                    dict.fromkeys(
                        window.evidence
                        for manifest in parent.coverage
                        if manifest.source == revision
                        for window in manifest.windows
                    )
                )
                if parent is not None
                else None
            )
            async for evidence in self._sources.iter_evidence(revision=revision, pinned=pinned):
                remaining -= len(evidence.excerpt.encode())
                if remaining < 0:
                    raise ResourceLimitError(
                        message="Select a corpus within the inference input budget."
                    )
                inputs.append(
                    InferenceInput(
                        text=evidence.excerpt,
                        evidence=(evidence.evidence,),
                        is_table=isinstance(evidence.part, ParsedTable),
                    )
                )
            if start == len(inputs):
                raise EvidenceUnavailableError
        return tuple(inputs)

    async def _execute(self, *, request: ExtractionRequest) -> DiscoveryDraft:
        context = request.context
        inputs = await self._inputs(
            revisions=request.revisions, parent=request.ancestry[0] if request.ancestry else None
        )
        corpus = tuple(citation for item in inputs for citation in item.evidence)
        fingerprint = hash_json(
            value=record_value(
                value=(
                    request.prompt,
                    context,
                    corpus,
                    *((tuple(draft.id for draft in request.ancestry),) if request.ancestry else ()),
                    *((request.schema_version,) if request.schema_version is not None else ()),
                    *(
                        (tuple(item.id for item in request.schema_sources),)
                        if request.schema_sources is not None
                        else ()
                    ),
                )
            )
        ).value
        intent = ExtractionIntent(
            id=DiscoveryDraftId(value=uuid4().hex),
            run_id=request.run_id or DiscoveryRunId(value=uuid4().hex),
            context=context,
            source_revisions=request.revisions,
            prompt=request.prompt,
            processing_fingerprint=fingerprint,
        )
        async with self._transaction() as transaction:
            await transaction.extraction.reserve(intent=intent)
        if request.schema_version == SCHEMA_V23:
            return await self._discover_schema(request=request, intent=intent, inputs=inputs)
        return await self._capture_observations(
            request=request, intent=intent, inputs=inputs, corpus=corpus
        )

    async def _discover_schema(
        self,
        *,
        request: ExtractionRequest,
        intent: ExtractionIntent,
        inputs: tuple[InferenceInput, ...],
    ) -> DiscoveryDraft:
        self.require_discovery()
        draft = DiscoveryDraft(
            id=intent.id,
            scope=intent.context.scope,
            run_id=intent.run_id,
            context=intent.context,
            source_revisions=intent.source_revisions,
            proposals=(),
            prompt=intent.prompt,
            processing_fingerprint=intent.processing_fingerprint,
            provenance=ExtractionProvenance(
                processing_fingerprint=intent.processing_fingerprint,
                extractor_id="domain-kernel/schema-discovery",
                extractor_version=SCHEMA_V23,
            ),
        )
        if request.schema_sources is None:
            return draft
        gateway = self._settings.gateway
        attempts = DISCOVERY_STAGE_ATTEMPTS
        if isinstance(gateway, DiscoveryStageLimits):
            attempts = min(attempts, gateway.discovery_stage_attempts)
        if "max_attempts" in self._settings.explicit_limits:
            attempts = min(attempts, self._settings.max_attempts)
        call = partial(
            self._schema_call,
            deadline=monotonic() + self._settings.timeout_seconds,
            attempts=attempts,
        )
        modeled = await CompactDiscovery(
            call=call,
            maximum=self._settings.max_proposals,
            max_input_bytes=self._settings.max_input_bytes,
            attempts=attempts,
        ).discover(intent=intent, draft=draft, inputs=inputs, previous=request.schema_prior)
        pack = await self._schema_reference_pack(context=intent.context)
        if pack is None or not modeled.proposals:
            return modeled
        prior_receipt = _SCHEMA_FRAME.validate_json(
            (request.schema_prior.schema_review_receipt if request.schema_prior else None) or "{}"
        )
        receipt = _SCHEMA_FRAME.validate_json(modeled.schema_review_receipt or "{}")
        cycle = receipt.get("repair_cycle") if prior_receipt.get("mapping_pending") else None
        try:
            compared = await schema_mapping.compare(
                draft=modeled,
                pack=pack,
                intent=intent,
                call=call,
                retry_cycle=cycle if isinstance(cycle, int) else None,
            )
        except (InferenceError, ResourceLimitError):
            return replace(
                modeled, schema_review_receipt=json.dumps({**receipt, "mapping_pending": True})
            )
        if (
            compared.proposals != modeled.proposals
            or compared.schema_questions != modeled.schema_questions
            or compared.schema_observations != modeled.schema_observations
        ):
            raise InferenceError(message="Reference comparison changed the frozen local draft.")
        return compared

    async def _capture_observations(
        self,
        *,
        request: ExtractionRequest,
        intent: ExtractionIntent,
        inputs: tuple[InferenceInput, ...],
        corpus: tuple[Evidence, ...],
    ) -> DiscoveryDraft:
        context = request.context
        fingerprint = intent.processing_fingerprint
        approved: tuple[JsonValue, ...] = tuple(
            {"name": item.name, "meaning": item.meaning, "kind": item.kind.value}
            for item in context.approved_definitions
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
                discovery_output_bytes=policy.max_output_bytes,
                discovery_continuation=continuation.select_windows(
                    previous=request.ancestry[0], inputs=inputs
                )
                if request.ancestry
                else (),
                discovery_pending_concepts=continuation.pending_concepts(
                    ancestry=request.ancestry, context=context
                ),
                scope=context.scope,
                approved_concept_pins=tuple(
                    (item.name, item.id.value, item.revision)
                    for item in context.approved_definitions
                    if item.kind.value == "concept"
                ),
                approved_concept_aliases=tuple(
                    (item.name, tuple(item.aliases))
                    for item in context.approved_definitions
                    if item.kind.value == "concept" and item.aliases
                ),
            ),
        )
        if (
            len(response.output_json.encode())
            + len((response.discovery_binding_json or "").encode())
            > policy.max_output_bytes
        ):
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
        bindings = ()
        if response.discovery_binding_json is None:
            gateway = self._settings.gateway
            if self.workflow_profile is not None and (
                not isinstance(gateway, BindingContractGateway) or gateway.binding_contract
            ):
                raise InferenceError(
                    message="The staged response is missing its endpoint bindings."
                )
            proposals = decode_proposals(
                output=response.output_json,
                context=context,
                corpus=corpus,
                provenance=provenance,
                max_proposals=policy.max_proposals if self._proposal_batch_size is None else None,
            )
        else:
            proposals, bindings = decode_bound_proposals(
                output=response.output_json,
                binding_json=response.discovery_binding_json,
                request=BoundProposalInput(
                    context=context,
                    inputs=inputs,
                    provenance=provenance,
                    run_id=intent.run_id,
                    max_proposals=policy.max_proposals,
                ),
            )
        coverage = self._decode_coverage(response=response, inputs=inputs)
        held, provisional = (
            decode_held_relationships(
                content=response.discovery_held_json, inputs=inputs, proposals=proposals
            )
            if response.discovery_held_json is not None
            else ((), {})
        )
        if request.ancestry:
            if not coverage:
                raise InferenceError(message="Use coverage receipts for a continuation draft.")
            coverage = continuation.merge_coverage(completed=coverage, previous=request.ancestry[0])
            proposals, deferred = continuation.delta(
                proposals=proposals,
                ancestry=request.ancestry,
                context=context,
                provisional_holds=provisional,
            )
            held += deferred
        elif provisional:
            raise InferenceError(
                message="Check provisional dependencies in a linked discovery run."
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
            relationship_bindings=bindings,
            coverage=coverage,
            held_relationships=held,
        )

    async def _schema_reference_pack(
        self,
        *,
        context: InterpretationContext,
    ) -> ReferencePack | None:
        if context.reference_pack is None:
            return None
        async with self._transaction() as transaction:
            if not isinstance(transaction, PackSelectionTransaction):
                raise MissingCapabilityError(
                    message="Resolve the captured reference pack for discovery."
                )
            pack = await transaction.packs.get(scope=context.scope)
            if pack is None or pack.pin != context.reference_pack:
                raise StaleStateError(message="The captured discovery reference pack has changed.")
        return pack

    async def _schema_call(  # noqa: PLR0913 - The request frame is part of replay identity.
        self,
        *,
        intent: ExtractionIntent,
        stage: str,
        instructions: str,
        schema: str,
        inputs: tuple[InferenceInput, ...],
        context_json: str,
        deadline: float,
        attempts: int,
    ) -> ModelResponse:
        policy = self._settings
        input_bytes = sum(len(item.text.encode()) for item in inputs)
        # Compact drafting has its own validation retries; each review pass gets one call.
        maximum = 1 if stage in COMPACT_STAGES else attempts
        for attempt in range(maximum):
            frame = (
                context_json
                if attempt == 0
                else json.dumps(
                    {**_SCHEMA_FRAME.validate_json(context_json), "attempt": attempt + 1},
                    ensure_ascii=False,
                )
            )
            if len(frame.encode()) + input_bytes > policy.max_input_bytes:
                raise ResourceLimitError(
                    message="Keep the schema evidence and context within the input budget."
                )
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise InferenceError(message="The discovery inference budget expired.")
            request = ModelRequest(
                request_id=f"{intent.run_id.value}/{intent.processing_fingerprint}/{stage}",
                inputs=inputs,
                context_json=frame,
                instructions=instructions,
                response_schema_json=schema,
                provider_stage=stage,
                scope=intent.context.scope,
                timeout_seconds=min(remaining, DISCOVERY_STAGE_TIMEOUT_SECONDS),
                discovery_output_bytes=policy.max_output_bytes,
            )
            try:
                response = await self._attempt(request=request)
            except InferenceError as error:
                if not error.retryable or attempt + 1 == maximum:
                    raise
            else:
                break
        else:
            raise AssertionError("Configure at least one discovery attempt.")
        if len(response.output_json.encode()) > policy.max_output_bytes:
            raise InferenceError(
                message="Keep the schema response within the configured output budget."
            )
        return response

    def _decode_coverage(
        self, *, response: ModelResponse, inputs: tuple[InferenceInput, ...]
    ) -> tuple[DiscoveryCoverage, ...]:
        return (
            omission_windows.decode(content=response.discovery_coverage_json, inputs=inputs)
            if response.discovery_coverage_json is not None
            else ()
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
            RuntimeTypeValidation.require_exact(
                value=response, expected=ModelResponse, field="Provider response"
            )
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
