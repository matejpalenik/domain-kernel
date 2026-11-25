"""Read named type, direction and inverse signals from one pinned reference pack."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.enums.semantic_relation import SemanticRelation
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.reference_packs.domain.contracts import ReferenceDefinition
    from domain_kernel.shared.contracts import DefinitionReference

_DOMAIN = "http://www.w3.org/2000/01/rdf-schema#domain"
_RANGE = "http://www.w3.org/2000/01/rdf-schema#range"
_WORD = re.compile(r"[^\W_]+")


@final
class OntologyShortlist:
    """Index the explicit named axioms available in a caller-pinned reference pack."""

    def __init__(self, *, pack: ReferencePack, members: Sequence[ReferenceDefinition]) -> None:
        """Read already materialized RDF without consulting an external ontology."""
        self._members = {item.id: item for item in members}
        self._parents: dict[Iri, set[Iri]] = defaultdict(set)
        self._inverse: dict[Iri, set[Iri]] = defaultdict(set)
        self._domains: dict[Iri, set[Iri]] = defaultdict(set)
        self._ranges: dict[Iri, set[Iri]] = defaultdict(set)
        self._ancestors: dict[Iri, frozenset[Iri]] = {}
        statements = (
            *pack.ontology_statements,
            *(
                statement
                for closure in pack.ontologies
                for doc in closure.documents
                for statement in doc.statements
            ),
        )
        for statement in statements:
            subject, target = statement.subject, statement.object
            if not isinstance(subject, Iri) or not isinstance(target, Iri):
                continue
            match statement.predicate.value:
                case SemanticRelation.SUBCLASS_OF:
                    self._parents[subject].add(target)
                case SemanticRelation.INVERSE_OF:
                    self._inverse[subject].add(target)
                    self._inverse[target].add(subject)
                case value if value == _DOMAIN:
                    self._domains[subject].add(target)
                case value if value == _RANGE:
                    self._ranges[subject].add(target)
                case _:
                    pass

    def _superclasses(self, term: Iri) -> frozenset[Iri]:
        if term not in self._ancestors:
            seen: set[Iri] = set()
            pending = [term]
            while pending:
                node = pending.pop()
                if node not in seen:
                    seen.add(node)
                    pending.extend(self._parents.get(node, ()))
            self._ancestors[term] = frozenset(seen)
        return self._ancestors[term]

    def _types(self, definition: ReferenceDefinitionId | None) -> frozenset[Iri]:
        member = self._members.get(definition) if definition is not None else None
        if member is None:
            return frozenset()
        return frozenset(
            term.term_iri
            for term in member.ontology_terms
            if term.entity_kind is OntologyEntityKind.CLASS
        )

    def _implies(self, actual: frozenset[Iri], expected: set[Iri] | frozenset[Iri]) -> bool:
        return bool(
            actual
            and expected
            and all(
                any(term in self._superclasses(actual_type) for actual_type in actual)
                for term in expected
            )
        )

    def _slot(
        self,
        *,
        local: DefinitionReference,
        expected: DefinitionReference,
        alignments: Mapping[DefinitionId, ReferenceDefinitionId],
    ) -> tuple[int, frozenset[Iri]] | None:
        mapped = alignments.get(local) if isinstance(local, DefinitionId) else None
        types = self._types(mapped)
        if mapped is None or not isinstance(expected, ReferenceDefinitionId):
            return 0, types
        if mapped == expected:
            return 2, types
        return (1, types) if self._implies(types, self._types(expected)) else None

    def direction(
        self,
        *,
        local: RelationshipDefinition,
        reference: ReferenceDefinition,
        alignments: Mapping[DefinitionId, ReferenceDefinitionId],
    ) -> tuple[int, tuple[str, ...]] | None:
        """Return reviewed role compatibility and the labels of verified inverse members."""
        if not isinstance(target := reference.body, RelationshipDefinition):
            return None
        subject = self._slot(
            local=local.source_concept_id, expected=target.source_concept_id, alignments=alignments
        )
        object_ = self._slot(
            local=local.target_concept_id, expected=target.target_concept_id, alignments=alignments
        )
        if subject is None or object_ is None:
            return None
        properties = [
            term.term_iri
            for term in reference.ontology_terms
            if term.entity_kind is OntologyEntityKind.OBJECT_PROPERTY
        ]
        compatible = [
            prop
            for prop in properties
            if (
                not subject[1]
                or not self._domains.get(prop)
                or self._implies(subject[1], self._domains[prop])
            )
            and (
                not object_[1]
                or not self._ranges.get(prop)
                or self._implies(object_[1], self._ranges[prop])
            )
        ]
        if properties and not compatible:
            return None
        names = tuple(self._label(prop) for prop in compatible if self._inverse.get(prop))
        return subject[0] + object_[0], names

    @staticmethod
    def _label(prop: Iri) -> str:
        part = re.split(r"[/#]", prop.value)[-1]
        return " ".join(_WORD.findall(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", part).casefold()))
