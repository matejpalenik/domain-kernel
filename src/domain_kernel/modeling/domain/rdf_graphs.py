"""Map reviewed identities and application shapes into separate portable RDF roles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, final
from urllib.parse import quote

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.interchange import RDF_VOCABULARY, IdentityBinding
from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.enums.label_role import LabelRole
from domain_kernel.shared.domain.enums.semantic_graph_role import SemanticGraphRole
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.policies.rdf_order_policy import RdfOrderPolicy
from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.candidate_pin import CandidatePin
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.rule_definition import RuleDefinition
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
    from domain_kernel.shared.domain.types.semantic_term import SemanticTerm
    from domain_kernel.shared.domain.types.snapshot_reference import SnapshotReference
    from domain_kernel.shared.domain.value_objects.cardinality_rule import CardinalityRule
    from domain_kernel.shared.domain.value_objects.quantity_binding import QuantityBinding

DK = RDF_VOCABULARY.value
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
SH = "http://www.w3.org/ns/shacl#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
PROV = "http://www.w3.org/ns/prov#"
_UNSPECIFIED = Iri(value=f"{DK}Unspecified")


def _append(*, owner: Iri, segments: tuple[str, ...]) -> Iri:
    parts = (
        part.replace(".", "%2E") if part in (".", "..") else quote(part, safe="")
        for part in segments
    )
    return Iri(value=f"{owner.value.rstrip('/')}/" + "/".join(parts))


def model_iri(*, base: Iri, model: SnapshotReference) -> Iri:
    """Derive a stable model resource from opaque scope IDs only."""
    if isinstance(model, CandidatePin):
        return base
    location = _append(
        owner=base,
        segments=(
            "projects",
            model.scope.project_id.value,
            "models",
            model.scope.model_id.value,
        ),
    )
    return Iri(value=location.value + "/")


def definition_iri(*, base: Iri, identity: PinnedDefinitionReference) -> Iri:
    """Derive a stable term whose IRI does not contain a version or display label."""
    return _definition_resource(base=base, model=identity.model, identity=identity.definition_id)


def _definition_resource(
    *,
    base: Iri,
    model: SnapshotReference,
    identity: DefinitionId,
) -> Iri:
    return _append(
        owner=model_iri(base=base, model=model),
        segments=("definitions", identity.value),
    )


def graph_iri(*, base: Iri, model: ModelVersion, role: SemanticGraphRole) -> Iri:
    """Bind an exact published snapshot and graph role."""
    return _append(
        owner=model_iri(base=base, model=model), segments=("versions", model.version, role.value)
    )


def owner_pin(*, model: ModelVersion, definition: Definition) -> PinnedDefinitionReference:
    """Pin one member of the exact active graph."""
    return PinnedDefinitionReference(
        model=model,
        definition_id=definition.id,
        definition_revision=definition.revision,
    )


def _lit(*, value: str | int | bool, language: str | None = None) -> RdfLiteral:
    if isinstance(value, bool):
        return RdfLiteral(value="true" if value else "false", datatype=Iri(value=f"{XSD}boolean"))
    if isinstance(value, int):
        return RdfLiteral(value=str(value), datatype=Iri(value=f"{XSD}integer"))
    return RdfLiteral(value=value, language=language)


def _wire(*, value: object) -> RdfLiteral:
    return _lit(
        value=CanonicalJson.encode(value=RecordCodec.to_value(value=value, utc_times=True)).decode(
            "utf-8"
        )
    )


type _Resource = Iri | BlankNode
type _Value = Iri | BlankNode | RdfLiteral


@final
class _Graph:
    def __init__(self) -> None:
        self._triples: set[OntologyStatement] = set()

    def add(self, *, subject: _Resource, predicate: str, target: _Value) -> None:
        self._triples.add(
            OntologyStatement(subject=subject, predicate=Iri(value=predicate), object=target)
        )

    def edge(self, *, subject: _Resource, predicate: str, target: str) -> None:
        self.add(subject=subject, predicate=predicate, target=Iri(value=target))

    def text(
        self,
        *,
        subject: _Resource,
        predicate: str,
        value: str | int | bool,
        language: str | None = None,
    ) -> None:
        self.add(subject=subject, predicate=predicate, target=_lit(value=value, language=language))

    def kind(self, *, subject: _Resource, category: str) -> None:
        self.edge(subject=subject, predicate=f"{RDF}type", target=category)

    def freeze(self) -> tuple[OntologyStatement, ...]:
        return tuple(
            sorted(self._triples, key=lambda item: RdfOrderPolicy.statement_key(statement=item))
        )

    def sequence(self, *, owner: Iri, values: Sequence[_Value]) -> _Resource:
        nil = Iri(value=f"{RDF}nil")
        if not values:
            return nil
        prefix = Hashing.hash_json(value=owner.value).value.removeprefix("sha256:")
        nodes = tuple(BlankNode(id=f"list{prefix}_{index}") for index in range(len(values)))
        for node, value, following in zip(nodes, values, (*nodes[1:], nil), strict=True):
            self.add(subject=node, predicate=f"{RDF}first", target=value)
            self.add(subject=node, predicate=f"{RDF}rest", target=following)
        return nodes[0]


@dataclass(frozen=True, kw_only=True)
class RdfModelGraphs:
    """Pure mapping result for one exact release and its scoped graph names."""

    documents: Sequence[tuple[SemanticGraphRole, Sequence[OntologyStatement]]]
    identities: Sequence[IdentityBinding]
    locations: Sequence[tuple[Iri, tuple[str | int, ...]]]
    issues: tuple[Issue, ...] = ()


type _DefinitionKey = tuple[SnapshotReference, DefinitionId]


@final
class _Index:
    def __init__(self, *, base: Iri, definitions: Mapping[_DefinitionKey, Definition]) -> None:
        self.base = base
        self.definitions = definitions

    def resolve(self, *, owner: SnapshotReference, target: DefinitionReference) -> _DefinitionKey:
        if isinstance(target, DefinitionId):
            return owner, target
        if isinstance(target, PinnedDefinitionReference):
            key = (target.model, target.definition_id)
            if (
                key in self.definitions
                and self.definitions[key].revision == target.definition_revision
            ):
                return key
        raise ValueError("Resolve an exact active reference before RDF projection")

    def iri(self, *, owner: SnapshotReference, target: DefinitionReference) -> Iri:
        model, identity = self.resolve(owner=owner, target=target)
        return _definition_resource(base=self.base, model=model, identity=identity)

    def semantic(self, *, owner: SnapshotReference, target: SemanticTerm) -> Iri:
        if isinstance(target, OntologyTermReference):
            return target.term_iri
        resource = self.iri(owner=owner, target=target.definition)
        return (
            _append(owner=resource, segments=tuple(target.local_path))
            if target.local_path
            else resource
        )


def _labels(*, graph: _Graph, resource: Iri, definition: Definition) -> None:
    graph.text(subject=resource, predicate=f"{RDFS}label", value=definition.display_name)
    graph.text(subject=resource, predicate=f"{RDFS}comment", value=definition.meaning)
    for alias in definition.aliases:
        graph.text(subject=resource, predicate=f"{SKOS}altLabel", value=alias)
    predicates = {
        LabelRole.PREFERRED: "prefLabel",
        LabelRole.ALTERNATIVE: "altLabel",
        LabelRole.HIDDEN: "hiddenLabel",
    }
    for entry in definition.terminology.labels:
        graph.text(
            subject=resource,
            predicate=f"{SKOS}{predicates[entry.role]}",
            value=entry.text.value,
            language=entry.language.value,
        )
    for description in definition.terminology.descriptions:
        graph.text(
            subject=resource,
            predicate=f"{SKOS}definition",
            value=description.text.value,
            language=description.language.value,
        )


@final
class _Mapper:
    def __init__(self, *, index: _Index, source: DomainModelBundle | Candidate) -> None:
        self._index = index
        self._bundle = source if isinstance(source, DomainModelBundle) else None
        self._candidate = (
            source.publication.candidate if isinstance(source, DomainModelBundle) else source
        )
        self._owner: SnapshotReference = (
            source.model_version
            if isinstance(source, DomainModelBundle)
            else candidate_pin(candidate=source)
        )
        self._model_iri = model_iri(base=index.base, model=self._owner)
        self._graph = {role: _Graph() for role in SemanticGraphRole}
        self._ontology = self._graph[SemanticGraphRole.ONTOLOGY]
        self._metadata = self._graph[SemanticGraphRole.MODEL_METADATA]
        self._shapes = self._graph[SemanticGraphRole.INSTANCE_SHAPES]
        self._identities: list[IdentityBinding] = []
        self._issues: list[Issue] = []
        self._locations: dict[Iri, tuple[str | int, ...]] = {self._model_iri: ()}

    def map(self) -> RdfModelGraphs:
        """Map exact local records without following an IRI or executing inference."""
        self._model_metadata()
        self._model_shapes()
        for definition in sorted(
            self._candidate.content.definitions, key=lambda item: item.id.value
        ):
            self._definition(definition=definition)
        return RdfModelGraphs(
            documents=tuple((role, self._graph[role].freeze()) for role in SemanticGraphRole),
            identities=tuple(self._identities),
            locations=tuple(self._locations.items()),
            issues=tuple(self._issues),
        )

    def _model_metadata(self) -> None:
        source = self._model_iri
        self._ontology.kind(subject=source, category=f"{OWL}Ontology")
        self._metadata.text(
            subject=source,
            predicate=f"{RDFS}comment",
            value=self._candidate.description,
        )
        snapshot = source
        if self._bundle is not None:
            snapshot = self._publication_metadata(bundle=self._bundle)
        self._metadata.kind(subject=snapshot, category=f"{PROV}Entity")
        self._metadata.text(
            subject=snapshot,
            predicate=f"{DK}contentHash",
            value=self._owner.content_hash.value,
        )
        for record in self._candidate.dependencies:
            self._metadata.add(
                subject=snapshot,
                predicate=f"{DK}dependencyPin",
                target=_wire(value=record),
            )
        for alignment in (
            *self._candidate.content.reference_dispositions,
            *self._candidate.content.source_alignments,
        ):
            self._metadata.add(
                subject=snapshot,
                predicate=f"{DK}referenceAlignment",
                target=_wire(value=alignment),
            )

    def _publication_metadata(self, *, bundle: DomainModelBundle) -> Iri:
        source = self._model_iri
        snapshot = _append(owner=source, segments=("versions", bundle.version))
        self._metadata.add(subject=snapshot, predicate=f"{PROV}specializationOf", target=source)
        self._metadata.text(subject=snapshot, predicate=f"{DK}version", value=bundle.version)
        approved = bundle.approval
        agent = _append(owner=source, segments=("actors", approved.actor))
        self._metadata.kind(subject=agent, category=f"{PROV}Agent")
        self._metadata.text(subject=agent, predicate=f"{DK}actor", value=approved.actor)
        self._metadata.add(subject=snapshot, predicate=f"{PROV}wasAttributedTo", target=agent)
        self._metadata.add(
            subject=snapshot,
            predicate=f"{PROV}generatedAtTime",
            target=RdfLiteral(
                value=bundle.published_at.astimezone(UTC).isoformat(),
                datatype=Iri(value=f"{XSD}dateTime"),
            ),
        )
        self._metadata.text(
            subject=snapshot, predicate=f"{DK}approvalReason", value=approved.reason
        )
        return snapshot

    def _model_shapes(self) -> None:
        graph = self._graph[SemanticGraphRole.MODEL_SHAPES]
        shape = _append(owner=self._model_iri, segments=("model-shapes", "definition-revision"))
        graph.kind(subject=shape, category=f"{SH}NodeShape")
        graph.edge(subject=shape, predicate=f"{SH}targetClass", target=f"{DK}DefinitionRevision")
        for field, datatype in (("definitionId", "string"), ("revision", "integer")):
            restriction = _append(owner=shape, segments=(field,))
            graph.add(subject=shape, predicate=f"{SH}property", target=restriction)
            graph.edge(subject=restriction, predicate=f"{SH}path", target=f"{DK}{field}")
            graph.edge(subject=restriction, predicate=f"{SH}datatype", target=f"{XSD}{datatype}")
            graph.text(subject=restriction, predicate=f"{SH}minCount", value=1)
            graph.text(subject=restriction, predicate=f"{SH}maxCount", value=1)

    def _definition(self, *, definition: Definition) -> None:
        owner = (
            owner_pin(model=self._owner, definition=definition)
            if isinstance(self._owner, ModelVersion)
            else None
        )
        iri = _definition_resource(base=self._index.base, model=self._owner, identity=definition.id)
        version = _append(owner=iri, segments=("revisions", str(definition.revision)))
        path = ("definitions", definition.id.value)
        self._locations[iri] = self._locations[version] = path
        if owner is not None:
            self._identities.append(IdentityBinding(definition=owner, term_iri=iri))
        self._definition_metadata(iri=iri, version=version, definition=definition)
        graph = self._metadata
        body = definition.body
        labels = (
            self._ontology
            if isinstance(
                body,
                (
                    ConceptDefinition,
                    StructuredValueDefinition,
                    RelationshipDefinition,
                    UnitDefinition,
                ),
            )
            else graph
        )
        _labels(graph=labels, resource=iri, definition=definition)
        match body:
            case ConceptDefinition() | StructuredValueDefinition():
                self._class_fields(owner=owner, resource=iri, body=body)
            case RelationshipDefinition():
                self._relationship(resource=iri, body=body)
            case ValueSetDefinition():
                self._vocabulary(resource=iri, body=body)
            case UnitDefinition():
                self._ontology.kind(subject=iri, category=f"{DK}Unit")
                if body.symbol is not None:
                    self._ontology.text(subject=iri, predicate=f"{DK}symbol", value=body.symbol)
                self._term_pin(
                    resource=iri, predicate=f"{DK}provenanceTerm", term=body.ontology_term
                )
            case SemanticLinkDefinition():
                self._ontology.add(
                    subject=self._index.semantic(owner=self._owner, target=body.subject),
                    predicate=body.relation.value,
                    target=self._index.semantic(owner=self._owner, target=body.object),
                )
            case OntologyModuleDefinition():
                graph.add(
                    subject=iri,
                    predicate=f"{DK}adoptedClosure",
                    target=_wire(value=body.ontology.pin),
                )
            case RuleDefinition(cardinality=rule) if rule is not None:
                graph.kind(subject=iri, category=f"{DK}DescriptiveDefinition")
                graph.add(subject=iri, predicate=f"{DK}cardinalityRule", target=_wire(value=rule))
                self._cardinality_rule(resource=iri, rule=rule)
            case _:
                graph.kind(subject=iri, category=f"{DK}DescriptiveDefinition")

    def _definition_metadata(self, *, iri: Iri, version: Iri, definition: Definition) -> None:
        graph = self._metadata
        graph.kind(subject=version, category=f"{DK}DefinitionRevision")
        graph.text(subject=iri, predicate=f"{DK}displayName", value=definition.display_name)
        graph.text(subject=iri, predicate=f"{DK}meaning", value=definition.meaning)
        for alias in definition.aliases:
            graph.text(subject=iri, predicate=f"{DK}alias", value=alias)
        graph.add(subject=version, predicate=f"{PROV}specializationOf", target=iri)
        graph.text(subject=version, predicate=f"{DK}definitionId", value=definition.id.value)
        graph.text(subject=version, predicate=f"{DK}revision", value=definition.revision)
        graph.text(subject=version, predicate=f"{DK}lookupName", value=definition.name)
        graph.text(subject=version, predicate=f"{DK}definitionKind", value=definition.kind.value)
        for decision in definition.decision_ids:
            record = _append(owner=self._model_iri, segments=("decisions", decision.value))
            graph.kind(subject=record, category=f"{PROV}Activity")
            graph.add(subject=version, predicate=f"{PROV}wasGeneratedBy", target=record)
        body = definition.body
        if not isinstance(body, OntologyModuleDefinition):
            graph.add(subject=version, predicate=f"{DK}declaredBody", target=_wire(value=body))

    def _term_pin(
        self, *, resource: Iri, predicate: str, term: OntologyTermReference | None
    ) -> None:
        if term is not None:
            self._metadata.add(subject=resource, predicate=predicate, target=term.term_iri)
            self._metadata.add(subject=resource, predicate=f"{DK}termPin", target=_wire(value=term))

    def _vocabulary(self, *, resource: Iri, body: ValueSetDefinition) -> None:
        graph = self._metadata
        graph.kind(subject=resource, category=f"{DK}ValueSet")
        graph.text(subject=resource, predicate=f"{DK}membership", value=body.membership.value)
        for member in body.members:
            entry = _append(owner=resource, segments=("members", member.code.value))
            graph.add(subject=resource, predicate=f"{DK}member", target=entry)
            graph.text(subject=entry, predicate=f"{DK}code", value=member.code.value)
            graph.text(subject=entry, predicate=f"{RDFS}label", value=member.label.value)
            graph.text(subject=entry, predicate=f"{RDFS}comment", value=member.meaning.value)
            if member.unit is not None:
                graph.add(
                    subject=entry,
                    predicate=f"{DK}unit",
                    target=self._index.iri(owner=self._owner, target=member.unit),
                )
            self._term_pin(
                resource=entry, predicate=f"{DK}provenanceTerm", term=member.ontology_term
            )

    def _shape(self, *, resource: Iri) -> Iri:
        shape = _append(owner=resource, segments=("instance-shape",))
        self._shapes.kind(subject=shape, category=f"{SH}NodeShape")
        self._shapes.add(subject=shape, predicate=f"{SH}targetClass", target=resource)
        self._shapes.text(subject=shape, predicate=f"{SH}closed", value=False)
        return shape

    def _class_fields(
        self,
        *,
        owner: PinnedDefinitionReference | None,
        resource: Iri,
        body: ConceptDefinition | StructuredValueDefinition,
    ) -> None:
        self._ontology.kind(subject=resource, category=f"{RDFS}Class")
        shape = self._shape(resource=resource)
        for field in body.attributes:
            path = ("attributes", field.id.value)
            property_iri = _append(owner=resource, segments=path)
            self._locations[property_iri] = (*self._locations[resource], *path)
            if owner is not None:
                self._identities.append(
                    IdentityBinding(definition=owner, term_iri=property_iri, local_path=path)
                )
            self._field(resource=resource, shape=shape, field=field, iri=property_iri)
        if isinstance(body, ConceptDefinition):
            for key in body.keys:
                key_iri = _append(owner=resource, segments=("keys", key.id.value))
                self._metadata.add(subject=resource, predicate=f"{DK}key", target=key_iri)
                self._metadata.add(
                    subject=key_iri, predicate=f"{DK}declaredKey", target=_wire(value=key)
                )
        elif body.quantity is not None:
            self._quantity(resource=resource, binding=body.quantity)

    def _quantity(self, *, resource: Iri, binding: QuantityBinding) -> None:
        self._metadata.kind(subject=resource, category=f"{DK}Quantity")
        for label, identity in (("magnitude", binding.magnitude), ("unitField", binding.unit)):
            self._metadata.add(
                subject=resource,
                predicate=f"{DK}{label}",
                target=_append(owner=resource, segments=("attributes", identity.value)),
            )
        if binding.quantity_kind is None:
            self._metadata.add(subject=resource, predicate=f"{DK}quantityKind", target=_UNSPECIFIED)
        else:
            self._term_pin(
                resource=resource, predicate=f"{DK}quantityKind", term=binding.quantity_kind
            )

    def _field(self, *, resource: Iri, shape: Iri, field: AttributeDefinition, iri: Iri) -> None:
        ontology = self._ontology
        metadata = self._metadata
        ontology.kind(subject=iri, category=f"{RDF}Property")
        ontology.add(subject=iri, predicate=f"{RDFS}domain", target=resource)
        ontology.text(subject=iri, predicate=f"{RDFS}label", value=field.display_name)
        metadata.add(subject=resource, predicate=f"{DK}field", target=iri)
        metadata.text(subject=iri, predicate=f"{DK}lookupName", value=field.name)
        metadata.text(subject=iri, predicate=f"{DK}required", value=field.required)
        metadata.text(subject=iri, predicate=f"{DK}collection", value=field.collection.value)
        metadata.text(subject=iri, predicate=f"{DK}nullability", value=field.nullability.value)
        for label, bound in (("minItems", field.min_items), ("maxItems", field.max_items)):
            metadata.add(
                subject=iri,
                predicate=f"{DK}{label}",
                target=_UNSPECIFIED if bound is None else _lit(value=bound.value),
            )
        prop = _append(owner=iri, segments=("shape",))
        self._shapes.add(subject=shape, predicate=f"{SH}property", target=prop)
        self._shapes.add(subject=prop, predicate=f"{SH}path", target=iri)
        low = (
            int(field.required)
            if field.collection is CollectionKind.SINGLE
            else field.min_items.value
            if field.min_items is not None
            else 0
        )
        high = (
            1
            if field.collection is CollectionKind.SINGLE
            else field.max_items.value
            if field.max_items is not None
            else None
        )
        self._counts(shape=prop, minimum=low, maximum=high)
        self._value_shape(iri=iri, prop=prop, field=field)

    def _value_shape(self, *, iri: Iri, prop: Iri, field: AttributeDefinition) -> None:
        body = field.value_type
        if isinstance(body, ScalarValueType):
            dtype = "dateTime" if body.data_type is DataType.DATETIME else body.data_type.value
            self._ontology.edge(subject=iri, predicate=f"{RDFS}range", target=f"{XSD}{dtype}")
            self._shapes.edge(subject=prop, predicate=f"{SH}datatype", target=f"{XSD}{dtype}")
        elif isinstance(body, ValueSetType):
            self._value_set_shape(iri=iri, prop=prop, body=body)
        elif isinstance(body, ConceptReferenceType):
            target = self._index.iri(owner=self._owner, target=body.concept)
            self._ontology.add(subject=iri, predicate=f"{RDFS}range", target=target)
            self._shapes.add(subject=prop, predicate=f"{SH}class", target=target)
            self._shapes.edge(subject=prop, predicate=f"{SH}nodeKind", target=f"{SH}IRI")
        else:
            target = self._index.iri(owner=self._owner, target=body.structure)
            self._ontology.add(subject=iri, predicate=f"{RDFS}range", target=target)
            self._shapes.add(
                subject=prop,
                predicate=f"{SH}node",
                target=_append(owner=target, segments=("instance-shape",)),
            )
            self._shapes.edge(subject=prop, predicate=f"{SH}nodeKind", target=f"{SH}BlankNodeOrIRI")

    def _value_set_shape(self, *, iri: Iri, prop: Iri, body: ValueSetType) -> None:
        self._ontology.edge(subject=iri, predicate=f"{RDFS}range", target=f"{XSD}string")
        self._shapes.edge(subject=prop, predicate=f"{SH}datatype", target=f"{XSD}string")
        pinned = self._index.resolve(owner=self._owner, target=body.value_set)
        self._metadata.add(
            subject=iri,
            predicate=f"{DK}valueSet",
            target=_definition_resource(base=self._index.base, model=pinned[0], identity=pinned[1]),
        )
        vocabulary = self._index.definitions[pinned].body
        if (
            isinstance(vocabulary, ValueSetDefinition)
            and vocabulary.membership is ValueSetMembership.CLOSED
        ):
            allowed = tuple(_lit(value=item.code.value) for item in vocabulary.members)
            self._shapes.add(
                subject=prop,
                predicate=f"{SH}in",
                target=self._shapes.sequence(owner=prop, values=allowed),
            )

    def _counts(self, *, shape: Iri, minimum: int, maximum: int | None) -> None:
        if minimum > 0:
            self._shapes.text(subject=shape, predicate=f"{SH}minCount", value=minimum)
        if maximum is not None:
            self._shapes.text(subject=shape, predicate=f"{SH}maxCount", value=maximum)

    def _cardinality_rule(self, *, resource: Iri, rule: CardinalityRule) -> None:
        owner = self._owner
        focus_key = self._index.resolve(owner=owner, target=rule.focus)
        relationship_key = self._index.resolve(owner=owner, target=rule.relationship)
        focus = self._index.definitions[focus_key].body
        relation = self._index.definitions[relationship_key].body
        if not isinstance(focus, ConceptDefinition) or not isinstance(
            relation, RelationshipDefinition
        ):
            self._unsupported_rule(resource=resource)
            return
        if (
            self._index.resolve(owner=relationship_key[0], target=relation.source_concept_id)
            != focus_key
        ):
            self._unsupported_rule(resource=resource)
            return
        trigger = rule.when
        field = next((f for f in focus.attributes if trigger and f.id == trigger.attribute), None)
        if trigger is not None and (
            field is None
            or field.collection is not CollectionKind.SINGLE
            or not _compatible_trigger(field=field, value=trigger.value)
        ):
            self._unsupported_rule(resource=resource)
            return
        graph = self._shapes
        shape = _append(owner=resource, segments=("cardinality-shape",))
        target = self._index.iri(owner=owner, target=rule.applicable_class or rule.focus)
        self._locations[shape] = (*self._locations[resource], "cardinality")
        graph.kind(subject=shape, category=f"{SH}NodeShape")
        graph.add(subject=shape, predicate=f"{SH}targetClass", target=target)
        requirement = shape
        if trigger is not None:
            requirement = _append(owner=shape, segments=("requirement",))
            outside = _append(owner=shape, segments=("outside-scope",))
            trigger_shape = _append(owner=shape, segments=("trigger",))
            trigger_property = _append(owner=trigger_shape, segments=("property",))
            focus_iri = self._index.iri(owner=owner, target=rule.focus)
            graph.add(
                subject=shape,
                predicate=f"{SH}or",
                target=graph.sequence(owner=shape, values=(outside, requirement)),
            )
            graph.add(subject=outside, predicate=f"{SH}not", target=trigger_shape)
            graph.add(subject=trigger_shape, predicate=f"{SH}property", target=trigger_property)
            graph.add(
                subject=trigger_property,
                predicate=f"{SH}path",
                target=_append(owner=focus_iri, segments=("attributes", trigger.attribute.value)),
            )
            graph.add(
                subject=trigger_property,
                predicate=f"{SH}hasValue",
                target=_lit(value=trigger.value),
            )
        prop = _append(owner=requirement, segments=("relationship",))
        self._locations[prop] = self._locations[shape]
        graph.add(subject=requirement, predicate=f"{SH}property", target=prop)
        graph.add(
            subject=prop,
            predicate=f"{SH}path",
            target=self._index.iri(owner=owner, target=rule.relationship),
        )
        graph.add(
            subject=prop,
            predicate=f"{SH}class",
            target=self._index.iri(owner=relationship_key[0], target=relation.target_concept_id),
        )
        self._counts(
            shape=prop,
            minimum=rule.minimum.value if rule.minimum else 0,
            maximum=rule.maximum.value if rule.maximum else None,
        )

    def _unsupported_rule(self, *, resource: Iri) -> None:
        self._issues.append(
            Issue(
                code="unsupported_cardinality_rule",
                path=(*self._locations[resource], "cardinality"),
                message="Select an outgoing relationship and a compatible single-valued trigger.",
            )
        )

    def _relationship(self, *, resource: Iri, body: RelationshipDefinition) -> None:
        source = self._index.iri(owner=self._owner, target=body.source_concept_id)
        target = self._index.iri(owner=self._owner, target=body.target_concept_id)
        self._ontology.kind(subject=resource, category=f"{OWL}ObjectProperty")
        self._ontology.add(subject=resource, predicate=f"{RDFS}domain", target=source)
        self._ontology.add(subject=resource, predicate=f"{RDFS}range", target=target)
        identity = Hashing.hash_json(value=resource.value).value.removeprefix("sha256:")
        inverse = BlankNode(id=f"inverse{identity}")
        self._shapes.add(subject=inverse, predicate=f"{SH}inversePath", target=resource)
        for label, owner, peer, path, bounds in (
            ("outgoing", source, target, resource, body.cardinality.outgoing),
            ("incoming", target, source, inverse, body.cardinality.incoming),
        ):
            prop = _append(owner=resource, segments=("shape", label))
            self._shapes.add(
                subject=self._shape(resource=owner), predicate=f"{SH}property", target=prop
            )
            self._shapes.add(subject=prop, predicate=f"{SH}path", target=path)
            self._shapes.add(subject=prop, predicate=f"{SH}class", target=peer)
            self._counts(
                shape=prop,
                minimum=bounds.minimum.value,
                maximum=bounds.maximum.value if bounds.maximum is not None else None,
            )


def _compatible_trigger(*, field: AttributeDefinition, value: str | bool | int) -> bool:
    datatype = field.value_type
    if isinstance(datatype, ValueSetType):
        return isinstance(value, str)
    if isinstance(datatype, ScalarValueType):
        expected = {DataType.STRING: str, DataType.BOOLEAN: bool, DataType.INTEGER: int}.get(
            datatype.data_type
        )
        return type(value) is expected
    return False


def rdf_graphs(
    *,
    bundle: DomainModelBundle,
    archives: Sequence[DomainModelBundle],
    base: Iri,
) -> RdfModelGraphs:
    """Map all graph roles for one release using the exact materialized closure."""
    definitions: dict[_DefinitionKey, Definition] = {
        (archive.model_version, definition.id): definition
        for archive in archives
        for definition in archive.content.definitions
    }
    return _Mapper(index=_Index(base=base, definitions=definitions), source=bundle).map()


def candidate_pin(*, candidate: Candidate) -> CandidatePin:
    """Identify one exact unpublished validation input."""
    return CandidatePin(
        scope=candidate.scope, candidate_id=candidate.id, content_hash=candidate.content_hash
    )


def candidate_graphs(
    *,
    candidate: Candidate,
    archives: Sequence[DomainModelBundle],
    base: Iri,
) -> RdfModelGraphs:
    """Use the shared mapping for an unpublished candidate and exact dependencies."""
    root = candidate_pin(candidate=candidate)
    definitions: dict[_DefinitionKey, Definition] = {
        (root, definition.id): definition for definition in candidate.content.definitions
    }
    definitions.update(
        {
            (archive.model_version, definition.id): definition
            for archive in archives
            for definition in archive.content.definitions
        }
    )
    return _Mapper(index=_Index(base=base, definitions=definitions), source=candidate).map()
