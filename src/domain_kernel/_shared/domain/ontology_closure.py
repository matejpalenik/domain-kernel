"""Structural verification and canonical identity of an explicit ontology closure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.ontology_assets import (
    Iri,
    OntologyClosurePin,
    OntologyDocumentPin,
    OntologySyntax,
)
from domain_kernel._shared.domain.ontology_documents import OntologyDocument, ParsedOntology
from domain_kernel._shared.domain.ontology_errors import InvalidOntologyError
from domain_kernel._shared.domain.rdf import node_value, statement_key
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from domain_kernel._shared.domain.ontology_assets import OntologyTermReference
    from domain_kernel.shared.hashing import JsonValue


@dataclass(frozen=True, kw_only=True)
class OntologyImportBinding:
    """An OWL import resolved to an exact supplied document."""

    source: OntologyDocumentPin
    import_iri: Iri
    target: OntologyDocumentPin

    def __post_init__(self) -> None:
        """Require typed referring and imported document identities."""
        _check_binding(source=self.source, iri=self.import_iri, target=self.target)


@dataclass(frozen=True, kw_only=True)
class OntologyContextBinding:
    """A JSON-LD context consulted during one document's parse."""

    source: OntologyDocumentPin
    context_iri: Iri
    target: OntologyDocumentPin

    def __post_init__(self) -> None:
        """Require typed referring and context document identities."""
        _check_binding(source=self.source, iri=self.context_iri, target=self.target)


def _check_binding(*, source: OntologyDocumentPin, iri: Iri, target: OntologyDocumentPin) -> None:
    require_exact(value=source, expected=OntologyDocumentPin, field="Referring document")
    require_exact(value=iri, expected=Iri, field="Resolved dependency IRI")
    require_exact(value=target, expected=OntologyDocumentPin, field="Dependency document")


def pin_key(*, pin: OntologyDocumentPin) -> tuple[str, ...]:
    """Order pins by their exact original identity, including the selected graph."""
    return (
        pin.document_iri.value,
        pin.content_hash.value,
        pin.ontology_iri.value if pin.ontology_iri is not None else "",
        pin.version_iri.value if pin.version_iri is not None else "",
        *node_value(node=pin.ontology_graph),
    )


def aliases(*, pin: OntologyDocumentPin) -> frozenset[Iri]:
    """Return exact admissible spellings for a requested ontology dependency."""
    return frozenset(
        value
        for value in (pin.document_iri, pin.ontology_iri, pin.version_iri)
        if value is not None
    )


def _import_key(binding: OntologyImportBinding) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return pin_key(pin=binding.source), binding.import_iri.value, pin_key(pin=binding.target)


def _context_key(binding: OntologyContextBinding) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return pin_key(pin=binding.source), binding.context_iri.value, pin_key(pin=binding.target)


def closure_hash(
    *,
    root: OntologyDocumentPin,
    documents: Iterable[ParsedOntology],
    imports: Sequence[OntologyImportBinding],
    contexts: Sequence[OntologyContextBinding],
    resources: Sequence[OntologyDocument],
) -> ContentHash:
    """Hash sorted typed content and pins without importing a parser."""
    graph_values: tuple[JsonValue, ...] = tuple(
        (
            pin_key(pin=parsed.document.pin),
            parsed.document.syntax.value,
            parsed.parser_id,
            parsed.parser_version,
            tuple(statement_key(statement=item) for item in parsed.statements),
            tuple((term.term_iri.value, term.entity_kind.value) for term in parsed.terms),
        )
        for parsed in sorted(documents, key=lambda item: pin_key(pin=item.document.pin))
    )
    return hash_json(
        value=(
            "domain-kernel.ontology-closure.v1",
            pin_key(pin=root),
            graph_values,
            tuple(
                (pin_key(pin=x.source), x.import_iri.value, pin_key(pin=x.target))
                for x in sorted(imports, key=_import_key)
            ),
            tuple(
                (pin_key(pin=x.source), x.context_iri.value, pin_key(pin=x.target))
                for x in sorted(contexts, key=_context_key)
            ),
            tuple(
                (pin_key(pin=x.pin), x.syntax.value)
                for x in sorted(resources, key=lambda item: pin_key(pin=item.pin))
            ),
        )
    )


@dataclass(frozen=True, kw_only=True)
class OntologyClosure:
    """A complete, parser-independent inventory of reviewed RDF input material."""

    root: OntologyDocumentPin
    documents: Sequence[ParsedOntology] = field(repr=False)
    imports: Sequence[OntologyImportBinding]
    contexts: Sequence[OntologyContextBinding]
    resources: Sequence[OntologyDocument] = field(repr=False)
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject substituted, unconnected or inconsistent closure contents."""
        require_exact(value=self.root, expected=OntologyDocumentPin, field="Ontology root")
        require_exact(value=self.content_hash, expected=ContentHash, field="Ontology closure hash")
        documents = tuple(
            sorted(
                snapshot_sequence(
                    items=self.documents,
                    item_type=ParsedOntology,
                    field="Parsed closure documents",
                ),
                key=lambda item: pin_key(pin=item.document.pin),
            )
        )
        imports = tuple(
            sorted(
                snapshot_sequence(
                    items=self.imports,
                    item_type=OntologyImportBinding,
                    field="Ontology import bindings",
                ),
                key=_import_key,
            )
        )
        contexts = tuple(
            sorted(
                snapshot_sequence(
                    items=self.contexts,
                    item_type=OntologyContextBinding,
                    field="Ontology context bindings",
                ),
                key=_context_key,
            )
        )
        resources = tuple(
            sorted(
                snapshot_sequence(
                    items=self.resources,
                    item_type=OntologyDocument,
                    field="Used context resources",
                ),
                key=lambda item: pin_key(pin=item.pin),
            )
        )
        object.__setattr__(self, "documents", documents)
        object.__setattr__(self, "imports", imports)
        object.__setattr__(self, "contexts", contexts)
        object.__setattr__(self, "resources", resources)
        self._verify_bindings()
        if self.content_hash != closure_hash(
            root=self.root,
            documents=documents,
            imports=imports,
            contexts=contexts,
            resources=resources,
        ):
            raise InvalidOntologyError(message="Verify the exact ontology closure digest.")

    @property
    def pin(self) -> OntologyClosurePin:
        """Return the complete closure pin used by projections and dependencies."""
        return OntologyClosurePin(root=self.root, content_hash=self.content_hash)

    def _verify_bindings(self) -> None:
        documents = {item.document.pin: item for item in self.documents}
        contexts = {item.pin: item for item in self.resources}
        if self.root not in documents or len(documents) != len(self.documents):
            raise InvalidOntologyError(
                message="Supply one materialized document for each used pin."
            )
        if len(contexts) != len(self.resources) or {item.target for item in self.contexts} != set(
            contexts
        ):
            raise InvalidOntologyError(message="Include the exact used JSON-LD context resources.")
        requested_imports = {(x.document.pin, iri) for x in self.documents for iri in x.import_iris}
        requested_contexts = {
            (x.document.pin, iri) for x in self.documents for iri in x.context_iris
        }
        if (
            {(x.source, x.import_iri) for x in self.imports} != requested_imports
            or len(self.imports) != len(requested_imports)
            or {(x.source, x.context_iri) for x in self.contexts} != requested_contexts
            or len(self.contexts) != len(requested_contexts)
        ):
            raise InvalidOntologyError(
                message="Bind every declared import and context exactly once."
            )
        edges: dict[OntologyDocumentPin, list[OntologyDocumentPin]] = {}
        for link in self.imports:
            if link.target not in documents or link.import_iri not in aliases(pin=link.target):
                raise InvalidOntologyError(
                    message="Use the exact supplied pin for each OWL import."
                )
            edges.setdefault(link.source, []).append(link.target)
        for context in self.contexts:
            if (
                context.context_iri != context.target.document_iri
                or contexts[context.target].syntax is not OntologySyntax.JSONLD
            ):
                raise InvalidOntologyError(message="Use exact JSON-LD context document IRIs.")
        self._verify_reachable(edges=edges, documents=set(documents))

    def _verify_reachable(
        self,
        *,
        edges: dict[OntologyDocumentPin, list[OntologyDocumentPin]],
        documents: set[OntologyDocumentPin],
    ) -> None:
        visited: set[OntologyDocumentPin] = set()
        pending = [self.root]
        while pending:
            current = pending.pop()
            if current not in visited:
                visited.add(current)
                pending.extend(edges.get(current, ()))
        if visited != documents:
            raise InvalidOntologyError(
                message="Materialize only the reachable imported ontology documents."
            )


def materialized_terms(*, closures: Iterable[OntologyClosure]) -> frozenset[OntologyTermReference]:
    """Index original term identities and their exact declared kinds."""
    return frozenset(
        term for closure in closures for parsed in closure.documents for term in parsed.terms
    )
