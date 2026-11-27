"""Inspect the ontology closures and term pins recorded by reviewed definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
    OntologyTermReference,
)
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from domain_kernel.shared.domain.types.definition_body import DefinitionBody
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference


@final
class ShapeOntologyPolicy:
    """Inspect adopted ontologies and pinned terms in authored shapes."""

    @staticmethod
    def adopted_ontologies(*, bodies: Iterable[DefinitionBody]) -> tuple[OntologyClosure, ...]:
        """Collect reviewed formal modules from the supplied active graph."""
        return tuple(
            dict.fromkeys(
                body.ontology for body in bodies if isinstance(body, OntologyModuleDefinition)
            )
        )

    @staticmethod
    def ontology_issues(
        *,
        bodies: Mapping[DefinitionReference, DefinitionBody],
        resources: Sequence[OntologyClosure],
    ) -> tuple[Issue, ...]:
        """Report term pins absent from the adopted or supplied ontology closures."""
        terms = OntologyClosure.materialized_terms(
            closures=(*resources, *ShapeOntologyPolicy.adopted_ontologies(bodies=bodies.values()))
        )

        return tuple(
            Issue(
                code="ontology_term_missing",
                path=(
                    "definitions",
                    owner.definition_id.value
                    if isinstance(owner, PinnedDefinitionReference)
                    else owner.value,
                    "ontology_terms",
                    term.term_iri.value,
                ),
                message=(
                    "Supply the exact term kind in a reviewed module or selected reference pack."
                ),
            )
            for owner, body in bodies.items()
            for term in ShapeOntologyPolicy.shape_ontology_terms(body=body)
            if term not in terms
        )

    @staticmethod
    def shape_ontology_terms(*, body: DefinitionBody) -> tuple[OntologyTermReference, ...]:
        """Collect exact term pins without inferring unit or quantity semantics."""
        if isinstance(body, SemanticLinkDefinition):
            return tuple(
                term
                for term in (body.subject, body.object)
                if isinstance(term, OntologyTermReference)
            )

        if isinstance(body, UnitDefinition) and body.ontology_term is not None:
            return (body.ontology_term,)

        if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
            kind = body.quantity.quantity_kind
            return () if kind is None else (kind,)

        if isinstance(body, ValueSetDefinition):
            return tuple(
                member.ontology_term for member in body.members if member.ontology_term is not None
            )

        return ()
