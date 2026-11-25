"""Bound formal extraction and verify that returned modules have exact provenance."""

from __future__ import annotations

from asyncio import timeout
from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel.modeling.application.reasoning import within_ontology_limits
from domain_kernel.modeling.domain.semantics import OntologyModuleResult
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.module_capabilities import ModuleGuarantee
from domain_kernel.shared.domain.ontology_closure import (
    OntologyClosure,
    aliases,
    materialized_terms,
)
from domain_kernel.shared.domain.ontology_documents import OntologyCapabilities, OntologyLimits
from domain_kernel.shared.domain.ontology_errors import UnsupportedCapabilityError
from domain_kernel.shared.domain.reasoning_capabilities import SemanticStatus
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import DomainKernelError, ResourceLimitError
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from domain_kernel.modeling.application.ontology import OntologyModuleExtractor
    from domain_kernel.shared.domain.module_capabilities import (
        ModuleExtractionMethod,
        ModuleExtractionSupport,
    )
    from domain_kernel.shared.domain.ontology_assets import (
        Iri,
        OntologyDocumentPin,
        OntologyEntityKind,
        OntologyTermReference,
    )
    from domain_kernel.shared.domain.reasoning_capabilities import ReasoningProfile, SemanticRegime


async def extract_ontology_module(  # noqa: PLR0913 -- explicit public extraction options
    *,
    ontology: OntologyClosure,
    seeds: Sequence[OntologyTermReference],
    method: ModuleExtractionMethod,
    profile: ReasoningProfile,
    regime: SemanticRegime,
    ontology_iri: Iri,
    extractor: OntologyModuleExtractor,
    limits: OntologyLimits | None = None,
) -> OntologyModuleResult:
    """Extract through one selected host and return only a verified complete module."""
    require_exact(value=ontology, expected=OntologyClosure, field="Module source closure")
    capabilities = extractor.capabilities
    require_exact(value=capabilities, expected=OntologyCapabilities, field="Module capabilities")
    attempt = OntologyModuleResult(
        source_hash=ontology.content_hash,
        ontology_iri=ontology_iri,
        limits=OntologyLimits() if limits is None else limits,
        seeds=seeds,
        method=method,
        profile=profile,
        regime=regime,
        adapter=capabilities,
        status=SemanticStatus.UNSUPPORTED,
        guarantee=ModuleGuarantee.NONE,
        signature=(),
        ontology=None,
        issues=(),
    )
    support = next(
        (
            option
            for option in capabilities.extraction
            if (option.method, option.profile, option.regime) == (method, profile, regime)
        ),
        None,
    )
    source_terms = materialized_terms(closures=(ontology,))
    if not set(attempt.seeds) <= source_terms:
        raise ValueError("Select seeds declared in the exact supplied source closure")
    source_pins = _pins(closure=ontology)
    if any(ontology_iri in aliases(pin=pin) for pin in source_pins):
        raise ValueError("Choose a new distinct identity for the derived module")
    if support is None:
        return _unavailable(
            attempt=attempt,
            status=SemanticStatus.UNSUPPORTED,
            code="module_capability",
            message="Select an extractor supporting the exact method, profile and semantics.",
        )
    result = await _invoke(extractor=extractor, ontology=ontology, attempt=attempt)
    return _verify_result(
        result=result,
        attempt=attempt,
        support=support,
        source_terms=source_terms,
        source_pins=source_pins,
    )


def _verify_result(
    *,
    result: OntologyModuleResult,
    attempt: OntologyModuleResult,
    support: ModuleExtractionSupport,
    source_terms: frozenset[OntologyTermReference],
    source_pins: frozenset[OntologyDocumentPin],
) -> OntologyModuleResult:
    if type(result) is not OntologyModuleResult or result.fingerprint != attempt.fingerprint:
        return _mismatch(attempt=attempt)
    module = result.ontology
    if module is None:
        return result
    if (
        result.guarantee is not support.guarantee
        or not set(result.signature) <= source_terms
        or _signature(terms=result.signature)
        != _signature(terms=materialized_terms(closures=(module,)))
        or _substitutes_source(module=module, source=source_pins)
    ):
        return _mismatch(attempt=attempt)
    if not within_ontology_limits(closures=(module,), limits=attempt.limits):
        return _bounded_outcome(attempt=attempt)
    if source_pins.intersection(parsed.document.pin for parsed in module.documents):
        return replace(
            result,
            guarantee=ModuleGuarantee.NONE,
            issues=(
                *result.issues,
                Issue(
                    code="module_retains_source_imports",
                    path=("ontology", "imports"),
                    message="Inspect the exact retained source documents before review.",
                    severity=IssueSeverity.WARNING,
                ),
            ),
        )
    return result


def _pins(*, closure: OntologyClosure) -> frozenset[OntologyDocumentPin]:
    return frozenset(
        [parsed.document.pin for parsed in closure.documents]
        + [resource.pin for resource in closure.resources]
    )


def _signature(
    *, terms: Iterable[OntologyTermReference]
) -> frozenset[tuple[Iri, OntologyEntityKind]]:
    return frozenset((term.term_iri, term.entity_kind) for term in terms)


def _substitutes_source(*, module: OntologyClosure, source: frozenset[OntologyDocumentPin]) -> bool:
    original_aliases = {iri for pin in source for iri in aliases(pin=pin)}
    return any(
        original_aliases.intersection(aliases(pin=pin)) for pin in _pins(closure=module) - source
    )


async def _invoke(
    *,
    extractor: OntologyModuleExtractor,
    ontology: OntologyClosure,
    attempt: OntologyModuleResult,
) -> OntologyModuleResult:
    if not within_ontology_limits(closures=(ontology,), limits=attempt.limits):
        return _bounded_outcome(attempt=attempt)
    try:
        async with timeout(attempt.limits.timeout_ms / 1000):
            return await extractor.extract(
                ontology=ontology,
                seeds=attempt.seeds,
                method=attempt.method,
                profile=attempt.profile,
                regime=attempt.regime,
                ontology_iri=attempt.ontology_iri,
                limits=attempt.limits,
            )
    except TimeoutError:
        return _unavailable(
            attempt=attempt,
            status=SemanticStatus.TIMEOUT,
            code="module_timeout",
            message="Reduce the selected scope or explicitly increase the extraction time limit.",
        )
    except ResourceLimitError:
        return _bounded_outcome(attempt=attempt)
    except UnsupportedCapabilityError:
        return _unavailable(
            attempt=attempt,
            status=SemanticStatus.UNSUPPORTED,
            code="module_input_unsupported",
            message="Inspect the exact input against the extractor's advertised restrictions.",
        )
    except (DomainKernelError, OSError, ValueError, TypeError, RuntimeError):
        return _unavailable(
            attempt=attempt,
            status=SemanticStatus.FAILED,
            code="module_extraction_failed",
            message="Inspect the selected extractor and its exact input.",
        )


def _bounded_outcome(*, attempt: OntologyModuleResult) -> OntologyModuleResult:
    return _unavailable(
        attempt=attempt,
        status=SemanticStatus.INCOMPLETE,
        code="module_resource_limit",
        message="Reduce the scope or explicitly increase the module's applicable resource limits.",
    )


def _mismatch(*, attempt: OntologyModuleResult) -> OntologyModuleResult:
    return _unavailable(
        attempt=attempt,
        status=SemanticStatus.FAILED,
        code="module_result_mismatch",
        message="Return the exact option record, derived identity and source-backed signature.",
    )


def _unavailable(
    *, attempt: OntologyModuleResult, status: SemanticStatus, code: str, message: str
) -> OntologyModuleResult:
    return replace(
        attempt, status=status, issues=(Issue(code=code, path=("ontology",), message=message),)
    )
