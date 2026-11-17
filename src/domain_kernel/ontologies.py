"""Load original ontology resources without opening a workspace or a live locator."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic
from typing import TYPE_CHECKING, final

from domain_kernel._shared.domain.ontology_assets import Iri, OntologySyntax
from domain_kernel._shared.domain.ontology_closure import (
    OntologyClosure,
    OntologyContextBinding,
    OntologyImportBinding,
    aliases,
    closure_hash,
)
from domain_kernel._shared.domain.ontology_documents import (
    OntologyCapabilities,
    OntologyDocument,
    OntologyLimits,
    ParsedOntology,
)
from domain_kernel._shared.domain.ontology_errors import (
    InvalidOntologyError,
    UnsupportedCapabilityError,
)
from domain_kernel.modeling.application.module_extraction import extract_ontology_module
from domain_kernel.modeling.application.reasoning import reason_ontology
from domain_kernel.shared.errors import ResourceLimitError
from domain_kernel.shared.validation import require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.ontology_assets import OntologyDocumentPin
    from domain_kernel.modeling.application.ontology import OntologyAdapter


__all__ = [
    "extract_ontology_module",
    "load_ontology",
    "reason_ontology",
    "serialize_ontology",
    "transcode_ontology",
]


def _use_adapter(*, adapter: OntologyAdapter | None) -> OntologyAdapter:
    if adapter is not None:
        return adapter
    from domain_kernel.modeling.infrastructure.rdflib_adapter import (  # noqa: PLC0415 - Optional adapter.
        RdfLibAdapter,
    )

    return RdfLibAdapter()


def _remaining(*, limits: OntologyLimits, deadline: float, statements: int) -> OntologyLimits:
    remaining = int((deadline - monotonic()) * 1000)
    if remaining <= 0:
        raise ResourceLimitError(
            message="Use a smaller ontology closure or increase its time budget."
        )
    return replace(
        limits, timeout_ms=remaining, max_statements=max(1, limits.max_statements - statements)
    )


@final
class _ClosureLoader:
    def __init__(
        self,
        *,
        documents: tuple[OntologyDocument, ...],
        root: OntologyDocument,
        limits: OntologyLimits,
        adapter: OntologyAdapter,
    ) -> None:
        self.root = root
        self.documents = documents
        self.limits = limits
        self.adapter = adapter
        self.deadline = monotonic() + limits.timeout_ms / 1000
        self.choices: dict[Iri, list[OntologyDocument]] = {}
        self.context_choices: dict[Iri, list[OntologyDocument]] = {}
        for document in documents:
            for alias in aliases(pin=document.pin):
                self.choices.setdefault(alias, []).append(document)
            if document.syntax is OntologySyntax.JSONLD:
                self.context_choices.setdefault(document.pin.document_iri, []).append(document)

    @staticmethod
    def _resolve(*, iri: Iri, choices: dict[Iri, list[OntologyDocument]]) -> OntologyDocument:
        matches = choices.get(iri, ())
        if len(matches) != 1:
            raise InvalidOntologyError(
                message="Supply one exact pinned resource for each referenced import or context."
            )
        return matches[0]

    def load(self) -> OntologyClosure:
        capabilities = self.adapter.capabilities
        require_exact(
            value=capabilities, expected=OntologyCapabilities, field="Adapter capabilities"
        )
        done: dict[OntologyDocumentPin, ParsedOntology] = {}
        imports: list[OntologyImportBinding] = []
        contexts: list[OntologyContextBinding] = []
        used_resources: dict[OntologyDocumentPin, OntologyDocument] = {}
        pending = [self.root]
        statements = 0
        while pending:
            document = pending.pop()
            if document.pin in done:
                continue
            if document.syntax not in capabilities.parse_syntaxes:
                raise UnsupportedCapabilityError
            parsed = self.adapter.parse(
                document=document,
                resources=self.documents,
                limits=_remaining(
                    limits=self.limits, deadline=self.deadline, statements=statements
                ),
            )
            require_exact(value=parsed, expected=ParsedOntology, field="Adapter result")
            if (
                parsed.document != document
                or parsed.parser_id != capabilities.adapter_id
                or parsed.parser_version != capabilities.adapter_version
            ):
                raise InvalidOntologyError(
                    message="Use the adapter's exact original and provenance."
                )
            statements += len(parsed.statements)
            if statements > self.limits.max_statements:
                raise ResourceLimitError(message="Use a closure within the RDF statement budget.")
            done[document.pin] = parsed
            for iri in parsed.import_iris:
                target = self._resolve(iri=iri, choices=self.choices)
                imports.append(
                    OntologyImportBinding(source=document.pin, import_iri=iri, target=target.pin)
                )
                pending.append(target)
            for iri in parsed.context_iris:
                target = self._resolve(iri=iri, choices=self.context_choices)
                contexts.append(
                    OntologyContextBinding(source=document.pin, context_iri=iri, target=target.pin)
                )
                used_resources[target.pin] = target
        materialized = tuple(done.values())
        resources = tuple(used_resources.values())
        _ = _remaining(limits=self.limits, deadline=self.deadline, statements=statements)
        return OntologyClosure(
            root=self.root.pin,
            documents=materialized,
            imports=imports,
            contexts=contexts,
            resources=resources,
            content_hash=closure_hash(
                root=self.root.pin,
                documents=materialized,
                imports=imports,
                contexts=contexts,
                resources=resources,
            ),
        )


def load_ontology(
    *,
    document: OntologyDocument,
    resources: Sequence[OntologyDocument] = (),
    adapter: OntologyAdapter | None = None,
    limits: OntologyLimits | None = None,
) -> OntologyClosure:
    """Parse an original and resolve its complete graph closure from explicit pins."""
    require_exact(value=document, expected=OntologyDocument, field="Root ontology")
    supplied = snapshot_sequence(
        items=resources, item_type=OntologyDocument, field="Ontology resources"
    )
    budget = OntologyLimits() if limits is None else limits
    require_exact(value=budget, expected=OntologyLimits, field="Ontology limits")
    documents: dict[OntologyDocumentPin, OntologyDocument] = {document.pin: document}
    for item in supplied:
        if item.pin in documents and item != documents[item.pin]:
            raise InvalidOntologyError(message="Supply one exact syntax for each document pin.")
        documents[item.pin] = item
    if (
        len(documents) > budget.max_documents
        or sum(len(item.payload) for item in documents.values()) > budget.max_bytes
    ):
        raise ResourceLimitError(
            message="Use ontology resources within the document and byte budget."
        )
    return _ClosureLoader(
        documents=tuple(documents.values()),
        root=document,
        limits=budget,
        adapter=_use_adapter(adapter=adapter),
    ).load()


def serialize_ontology(
    *,
    ontology: ParsedOntology,
    syntax: OntologySyntax,
    document_iri: Iri,
    adapter: OntologyAdapter | None = None,
    limits: OntologyLimits | None = None,
) -> OntologyDocument:
    """Serialize the complete asserted dataset under a new original byte pin."""
    require_exact(value=ontology, expected=ParsedOntology, field="Parsed ontology")
    require_exact(value=syntax, expected=OntologySyntax, field="Target syntax")
    require_exact(value=document_iri, expected=Iri, field="Target document IRI")
    selected = _use_adapter(adapter=adapter)
    if syntax not in selected.capabilities.serialize_syntaxes:
        raise UnsupportedCapabilityError
    budget = OntologyLimits() if limits is None else limits
    require_exact(value=budget, expected=OntologyLimits, field="Ontology limits")
    if (
        len(ontology.statements) > budget.max_statements
        or len(ontology.document.payload) > budget.max_bytes
    ):
        raise ResourceLimitError(message="Use a dataset within the output budget.")
    result = selected.serialize(
        ontology=ontology, syntax=syntax, document_iri=document_iri, limits=budget
    )
    require_exact(value=result, expected=OntologyDocument, field="Serialized document")
    original = ontology.document.pin
    if (
        result.syntax is not syntax
        or result.pin.document_iri != document_iri
        or result.pin.ontology_iri != original.ontology_iri
        or result.pin.version_iri != original.version_iri
    ):
        raise InvalidOntologyError(
            message="Keep the exact ontology and version IRIs during serialization."
        )
    if len(result.payload) > budget.max_bytes:
        raise ResourceLimitError(message="Use serialization within the output byte budget.")
    return result


def transcode_ontology(  # noqa: PLR0913 - Source, target and explicit capabilities.
    *,
    document: OntologyDocument,
    syntax: OntologySyntax,
    document_iri: Iri,
    resources: Sequence[OntologyDocument] = (),
    adapter: OntologyAdapter | None = None,
    limits: OntologyLimits | None = None,
) -> OntologyDocument:
    """Load the exact closure and reserialize its root dataset."""
    selected = _use_adapter(adapter=adapter)
    loaded = load_ontology(document=document, resources=resources, adapter=selected, limits=limits)
    root = next(item for item in loaded.documents if item.document.pin == loaded.root)
    return serialize_ontology(
        ontology=root, syntax=syntax, document_iri=document_iri, adapter=selected, limits=limits
    )
