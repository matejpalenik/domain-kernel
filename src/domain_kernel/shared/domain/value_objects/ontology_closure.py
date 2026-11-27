"""A complete, parser-independent inventory of reviewed RDF input material."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.policies.ontology_pins_policy import OntologyPinsPolicy
from domain_kernel.shared.domain.policies.rdf_order_policy import RdfOrderPolicy
from domain_kernel.shared.domain.value_objects.ontology_closure_pin import OntologyClosurePin
from domain_kernel.shared.domain.value_objects.ontology_context_binding import (
    OntologyContextBinding,
)
from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.domain.value_objects.ontology_import_binding import OntologyImportBinding
from domain_kernel.shared.domain.value_objects.parsed_ontology import ParsedOntology
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
        OntologyTermReference,
    )
    from domain_kernel.shared.json_value import JsonValue


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
        RuntimeTypeValidation.require_exact(
            value=self.root, expected=OntologyDocumentPin, field="Ontology root"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Ontology closure hash"
        )

        documents = tuple(
            sorted(
                SequenceValidation.snapshot_sequence(
                    items=self.documents,
                    item_type=ParsedOntology,
                    field="Parsed closure documents",
                ),
                key=lambda item: OntologyPinsPolicy.pin_key(pin=item.document.pin),
            )
        )
        imports = tuple(
            sorted(
                SequenceValidation.snapshot_sequence(
                    items=self.imports,
                    item_type=OntologyImportBinding,
                    field="Ontology import bindings",
                ),
                key=OntologyClosure._import_key,
            )
        )
        contexts = tuple(
            sorted(
                SequenceValidation.snapshot_sequence(
                    items=self.contexts,
                    item_type=OntologyContextBinding,
                    field="Ontology context bindings",
                ),
                key=OntologyClosure._context_key,
            )
        )
        resources = tuple(
            sorted(
                SequenceValidation.snapshot_sequence(
                    items=self.resources,
                    item_type=OntologyDocument,
                    field="Used context resources",
                ),
                key=lambda item: OntologyPinsPolicy.pin_key(pin=item.pin),
            )
        )

        object.__setattr__(self, "documents", documents)
        object.__setattr__(self, "imports", imports)
        object.__setattr__(self, "contexts", contexts)
        object.__setattr__(self, "resources", resources)

        self._verify_bindings()

        if self.content_hash != OntologyClosure.compute_hash(
            root=self.root,
            documents=documents,
            imports=imports,
            contexts=contexts,
            resources=resources,
        ):
            raise InvalidOntologyError(message="Verify the exact ontology closure digest.")

    @property
    def pin(self) -> OntologyClosurePin:
        """The complete closure pin used by projections and dependencies."""
        return OntologyClosurePin(root=self.root, content_hash=self.content_hash)

    def _verify_bindings(self) -> None:
        """Validate closure edges against the exact captured resource pins."""
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
            if link.target not in documents or link.import_iri not in OntologyPinsPolicy.aliases(
                pin=link.target
            ):
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
        """Require every captured resource to be reachable from the declared root."""
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

    @staticmethod
    def _import_key(binding: OntologyImportBinding) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """Return the stable ordering key for an ontology import binding."""
        return (
            OntologyPinsPolicy.pin_key(pin=binding.source),
            binding.import_iri.value,
            OntologyPinsPolicy.pin_key(pin=binding.target),
        )

    @staticmethod
    def _context_key(
        binding: OntologyContextBinding,
    ) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """Return the stable ordering key for an ontology context binding."""
        return (
            OntologyPinsPolicy.pin_key(pin=binding.source),
            binding.context_iri.value,
            OntologyPinsPolicy.pin_key(pin=binding.target),
        )

    @staticmethod
    def compute_hash(
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
                OntologyPinsPolicy.pin_key(pin=parsed.document.pin),
                parsed.document.syntax.value,
                parsed.parser_id,
                parsed.parser_version,
                tuple(RdfOrderPolicy.statement_key(statement=item) for item in parsed.statements),
                tuple((term.term_iri.value, term.entity_kind.value) for term in parsed.terms),
            )
            for parsed in sorted(
                documents, key=lambda item: OntologyPinsPolicy.pin_key(pin=item.document.pin)
            )
        )

        return Hashing.hash_json(
            value=(
                "domain-kernel.ontology-closure.v1",
                OntologyPinsPolicy.pin_key(pin=root),
                graph_values,
                tuple(
                    (
                        OntologyPinsPolicy.pin_key(pin=x.source),
                        x.import_iri.value,
                        OntologyPinsPolicy.pin_key(pin=x.target),
                    )
                    for x in sorted(imports, key=OntologyClosure._import_key)
                ),
                tuple(
                    (
                        OntologyPinsPolicy.pin_key(pin=x.source),
                        x.context_iri.value,
                        OntologyPinsPolicy.pin_key(pin=x.target),
                    )
                    for x in sorted(contexts, key=OntologyClosure._context_key)
                ),
                tuple(
                    (OntologyPinsPolicy.pin_key(pin=x.pin), x.syntax.value)
                    for x in sorted(
                        resources, key=lambda item: OntologyPinsPolicy.pin_key(pin=item.pin)
                    )
                ),
            )
        )

    @staticmethod
    def materialized_terms(
        *, closures: Iterable[OntologyClosure]
    ) -> frozenset[OntologyTermReference]:
        """Index original term identities and their exact declared kinds."""
        return frozenset(
            term for closure in closures for parsed in closure.documents for term in parsed.terms
        )
