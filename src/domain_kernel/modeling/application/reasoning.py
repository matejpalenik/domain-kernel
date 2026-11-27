"""Bound explicit reasoning and verify every result against captured inputs."""

from __future__ import annotations

from asyncio import timeout
from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.semantics import ReasoningRequest, ReasoningResult
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.enums.semantic_status import SemanticStatus
from domain_kernel.shared.domain.value_objects.ontology_capabilities import OntologyCapabilities
from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
from domain_kernel.shared.errors.domain_kernel_error import DomainKernelError
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.application.ontology import OntologyReasoner


def within_ontology_limits(*, closures: Sequence[OntologyClosure], limits: OntologyLimits) -> bool:
    """Bound input documents, original bytes and statements across the complete request."""
    parsed = [doc for closure in closures for doc in closure.documents]
    resources = [doc for closure in closures for doc in closure.resources]
    return (
        len(parsed) + len(resources) <= limits.max_documents
        and sum(len(doc.document.payload) for doc in parsed)
        + sum(len(doc.payload) for doc in resources)
        <= limits.max_bytes
        and sum(len(doc.statements) for doc in parsed) <= limits.max_statements
    )


def _engine_failure(*, error: Exception) -> tuple[SemanticStatus, str, str]:
    if isinstance(error, TimeoutError):
        return (
            SemanticStatus.TIMEOUT,
            "reasoning_timeout",
            "Reduce the closure or explicitly increase the reasoning time limit.",
        )
    if isinstance(error, UnsupportedCapabilityError):
        return (
            SemanticStatus.UNSUPPORTED,
            "reasoning_input_unsupported",
            "Inspect the exact input against the reasoner's advertised restrictions.",
        )
    if isinstance(error, ResourceLimitError):
        return (
            SemanticStatus.INCOMPLETE,
            "reasoning_limit",
            "Reduce the input or explicitly increase the applicable reasoning limits.",
        )
    return (
        SemanticStatus.FAILED,
        "reasoning_failed",
        "Inspect the selected reasoner and its exact input.",
    )


async def reason_ontology(
    *,
    ontology: OntologyClosure,
    request: ReasoningRequest,
    reasoner: OntologyReasoner,
    limits: OntologyLimits | None = None,
) -> ReasoningResult:
    """Ask a selected reasoner about exact supplied material without resolving live IRIs."""
    bounds = OntologyLimits() if limits is None else limits
    RuntimeTypeValidation.require_exact(
        value=bounds, expected=OntologyLimits, field="Reasoning limits"
    )
    RuntimeTypeValidation.require_exact(
        value=ontology, expected=OntologyClosure, field="Ontology closure"
    )
    RuntimeTypeValidation.require_exact(
        value=request, expected=ReasoningRequest, field="Reasoning request"
    )
    capabilities = reasoner.capabilities
    RuntimeTypeValidation.require_exact(
        value=capabilities, expected=OntologyCapabilities, field="Reasoner capabilities"
    )

    def unavailable(*, status: SemanticStatus, code: str, message: str) -> ReasoningResult:
        return ReasoningResult(
            input_hash=ontology.content_hash,
            request=request,
            adapter=capabilities,
            limits=bounds,
            status=status,
            consistent=None,
            entailed=None,
            unsatisfiable=(),
            inferred=(),
            issues=(Issue(code=code, path=("reasoning",), message=message),),
        )

    terms = OntologyClosure.materialized_terms(closures=(ontology,))
    if not set(request.signature) <= terms:
        raise ValueError("Select named classes from the exact verified input closure")
    support = next(
        (
            item
            for item in capabilities.reasoning
            if (item.profile, item.regime, item.task)
            == (request.profile, request.regime, request.task)
        ),
        None,
    )
    if support is None:
        return unavailable(
            status=SemanticStatus.UNSUPPORTED,
            code="reasoning_unsupported",
            message="Select a reasoner supporting this profile, semantic regime and task.",
        )
    inputs = (ontology,) if request.query is None else (ontology, request.query)
    try:
        async with timeout(bounds.timeout_ms / 1000):
            result = await _bounded_reason(
                inputs=inputs, request=request, reasoner=reasoner, limits=bounds
            )
    except (DomainKernelError, OSError, ValueError, TypeError, RuntimeError) as error:
        status, code, message = _engine_failure(error=error)
        return unavailable(status=status, code=code, message=message)
    if (
        type(result) is not ReasoningResult
        or result.input_hash != ontology.content_hash
        or result.request != request
        or result.adapter != capabilities
        or result.limits != bounds
        or not set(result.unsatisfiable) <= (set(request.signature) if request.signature else terms)
    ):
        return unavailable(
            status=SemanticStatus.FAILED,
            code="reasoning_result_mismatch",
            message="Return results for the exact captured input, request, engine and limits.",
        )
    if len(result.inferred) + len(result.unsatisfiable) > bounds.max_statements:
        return unavailable(
            status=SemanticStatus.INCOMPLETE,
            code="reasoning_output_limit",
            message="Select fewer classes or explicitly increase the reasoning output limit.",
        )
    if result.status is SemanticStatus.COMPLETE and not support.complete:
        return replace(
            result,
            status=SemanticStatus.INCOMPLETE,
            issues=(
                *result.issues,
                Issue(
                    code="reasoning_partial_capability",
                    path=("reasoning",),
                    message="Select a complete reasoner for the requested semantics and task.",
                ),
            ),
        )
    return result


async def _bounded_reason(
    *,
    inputs: tuple[OntologyClosure, ...],
    request: ReasoningRequest,
    reasoner: OntologyReasoner,
    limits: OntologyLimits,
) -> ReasoningResult:
    if not within_ontology_limits(closures=inputs, limits=limits):
        raise ResourceLimitError
    return await reasoner.reason(ontology=inputs[0], request=request, limits=limits)
