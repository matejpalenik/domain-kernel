"""Typed projection requests, diagnostics and exact generated graph identities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.shared.contracts import (
    CandidatePin,
    Issue,
    ModelVersion,
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.artifacts import ProjectionMetadata, SemanticGraphRole
from domain_kernel.shared.domain.definitions import Definition, UnitDefinition
from domain_kernel.shared.domain.model_values import BusinessCode, MeaningText, Terminology
from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.domain.ontology_assets import Iri, OntologyClosurePin
from domain_kernel.shared.domain.ontology_closure import OntologyClosure
from domain_kernel.shared.domain.ontology_errors import UnsupportedCapabilityError
from domain_kernel.shared.domain.rdf import OntologyStatement
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import CompanyDefinitionReference
    from domain_kernel.shared.domain.artifacts import ConsumerObligation
    from domain_kernel.shared.domain.definitions import (
        ConceptDefinition,
        StructuredValueDefinition,
    )

_ADAPTER_VERSION_ARITY = 2

RDF_MAPPING = MappingId(value="dk-rdf/1.0")
RDF_VOCABULARY = Iri(value="https://domain-kernel.invalid/vocabulary/dk-rdf/1.0#")
JSON_SCHEMA_MAPPING = MappingId(value="dk-json-schema/1.0")
LINKML_MAPPING = MappingId(value="dk-linkml/1.0")


@unique
class RdfSyntax(StrEnum):
    """Portable graph document representations."""

    TURTLE = "turtle"
    JSONLD = "jsonld"


@unique
class LinkmlSyntax(StrEnum):
    """Portable LinkML schema document representations."""

    YAML = "yaml"
    JSON = "json"


def require_projection_base(*, value: Iri) -> None:
    """Require a slash-terminated host-supplied HTTP(S) identity namespace."""
    require_exact(value=value, expected=Iri, field="Projection base IRI")
    parsed = urlsplit(value.value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.query
        or parsed.fragment
        or not value.value.endswith("/")
    ):
        raise ValueError("Use an absolute HTTP(S) base IRI ending in a slash")


@dataclass(frozen=True, kw_only=True)
class RdfProjectionRequest:
    """Select all semantic roles and the full exact published dependency closure."""

    base_iri: Iri
    syntax: RdfSyntax = RdfSyntax.TURTLE
    mapping: MappingId = RDF_MAPPING
    kind: Literal["rdf_projection"] = "rdf_projection"

    def __post_init__(self) -> None:
        """Preserve nominal mapping, syntax and base identity."""
        require_projection_base(value=self.base_iri)
        require_exact(value=self.syntax, expected=RdfSyntax, field="RDF syntax")
        require_exact(value=self.mapping, expected=MappingId, field="RDF mapping")
        require_exact(value=self.kind, expected=str, field="Projection request kind")
        if self.kind != "rdf_projection":
            raise ValueError("Select the RDF projection request kind")


@dataclass(frozen=True, kw_only=True)
class JsonSchemaProjectionRequest:
    """Select a concept or structured value in one exact published closure."""

    root: (
        Definition[ConceptDefinition]
        | Definition[StructuredValueDefinition]
        | CompanyDefinitionReference
    )
    base_iri: Iri
    kind: Literal["json_schema_projection"] = "json_schema_projection"

    def __post_init__(self) -> None:
        """Check the base, root selector and closed discriminator."""
        require_projection_base(value=self.base_iri)
        _require_schema_root(root=self.root)
        require_exact(value=self.kind, expected=str, field="Projection request kind")
        if self.kind != "json_schema_projection":
            raise ValueError("Select the JSON Schema projection request kind")


def _require_schema_root(*, root: object) -> None:
    if not isinstance(root, (Definition, DefinitionId, PinnedDefinitionReference)):
        raise TypeError("Select an inspected definition, local ID or exact pinned root")


@dataclass(frozen=True, kw_only=True)
class LinkmlProjectionRequest:
    """Select a published definition closure for LinkML interchange."""

    base_iri: Iri
    definition_ids: Sequence[DefinitionId] | None = None
    syntax: LinkmlSyntax = LinkmlSyntax.YAML
    mapping: MappingId = LINKML_MAPPING
    kind: Literal["linkml_projection"] = "linkml_projection"

    def __post_init__(self) -> None:
        """Capture the caller's exact selection and requested mapping."""
        require_projection_base(value=self.base_iri)
        require_exact(value=self.syntax, expected=LinkmlSyntax, field="LinkML syntax")
        require_exact(value=self.mapping, expected=MappingId, field="LinkML mapping")
        require_exact(value=self.kind, expected=str, field="Projection request kind")
        if self.kind != "linkml_projection":
            raise ValueError("Select the LinkML projection request kind")
        if self.definition_ids is not None:
            selection = snapshot_sequence(
                items=self.definition_ids, item_type=DefinitionId, field="LinkML selection"
            )
            if not selection or len(set(selection)) != len(selection):
                raise ValueError("Select one or more distinct definitions")
            object.__setattr__(self, "definition_ids", selection)


type ProjectionRequest = (
    JsonSchemaProjectionRequest | RdfProjectionRequest | LinkmlProjectionRequest
)


def require_projection_request(*, request: object) -> None:
    """Reject requests without a registered exact projection type."""
    if type(request) not in (
        JsonSchemaProjectionRequest,
        LinkmlProjectionRequest,
        RdfProjectionRequest,
    ):
        raise TypeError("Select a registered projection request")


@unique
class ProjectionAvailability(StrEnum):
    """Whether a complete analysis is available for this request."""

    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    UNSUPPORTED_MAPPING = "unsupported_mapping"
    FAILED = "failed"


@unique
class ProjectionFeature(StrEnum):
    """Semantic parts of a projected definition that need explicit assessment."""

    DEFINITION = "definition"
    CONSTRAINT = "constraint"
    VALUE_TYPE = "value_type"
    KNOWN_CODES = "known_codes"
    FIELD_PRESENCE = "field_presence"
    COLLECTION_KIND = "collection_kind"
    ITEM_BOUNDS = "item_bounds"
    VALUE_EQUALITY = "value_equality"
    NULLABILITY = "nullability"
    KEY = "key"
    RELATIONSHIP = "relationship"
    REFERENCE_TARGET = "reference_target"
    TERMINOLOGY = "terminology"
    QUANTITY_BINDING = "quantity_binding"
    UNIT_DEFINITION = "unit_definition"
    UNIT_REFERENCE = "unit_reference"
    DECIMAL_FACETS = "decimal_facets"
    FORMAL_SEMANTICS = "formal_semantics"
    MODEL_CHECK = "model_check"


@unique
class RepresentationSupport(StrEnum):
    """How the chosen target carries one feature."""

    NATIVE = "native"
    ANNOTATED = "annotated"
    UNSUPPORTED = "unsupported"


@unique
class ValidationResponsibility(StrEnum):
    """Which participant can enforce a represented feature."""

    TARGET = "target"
    HOST = "host"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


@unique
class ProjectionRemedy(StrEnum):
    """Supported next steps for a projection diagnostic."""

    ENFORCE_IN_HOST = "enforce_in_host"
    USE_COMPLETE_BUNDLE = "use_complete_bundle"
    SELECT_SUPPORTED_TARGET = "select_supported_target"
    AUTHOR_REVIEWED_DERIVATION = "author_reviewed_derivation"
    INSTALL_OPTIONAL_DEPENDENCY = "install_optional_dependency"
    SELECT_SUPPORTED_MAPPING = "select_supported_mapping"
    INSPECT_DIAGNOSTICS = "inspect_diagnostics"


@dataclass(frozen=True, kw_only=True)
class ProjectionLocation:
    """Exact release definition and optional nominal local member."""

    definition: PinnedDefinitionReference
    member: AttributeId | KeyId | BusinessCode | None = None

    def __post_init__(self) -> None:
        """Check the declared location kinds."""
        require_exact(value=self.definition, expected=PinnedDefinitionReference, field="Owner")
        if self.member is not None and type(self.member) not in (AttributeId, KeyId, BusinessCode):
            raise TypeError("Choose an exact attribute, key or value-set code")


@dataclass(frozen=True, kw_only=True)
class MappingDescriptor:
    """A versioned mapping vocabulary and the exact selected adapter versions."""

    id: MappingId
    vocabulary_iri: Iri
    supported_capabilities: Sequence[str]
    adapter_versions: Sequence[tuple[str, str]]

    def __post_init__(self) -> None:
        """Detach and verify every fingerprint."""
        require_exact(value=self.id, expected=MappingId, field="Mapping ID")
        require_exact(value=self.vocabulary_iri, expected=Iri, field="Vocabulary IRI")
        capabilities = snapshot_sequence(
            items=self.supported_capabilities,
            item_type=str,
            field="Mapping capabilities",
        )
        if not is_non_string_sequence(self.adapter_versions):
            raise TypeError("Supply a sequence of adapter versions")
        versions = tuple(self.adapter_versions)
        for pair in versions:
            if type(pair) is not tuple or len(pair) != _ADAPTER_VERSION_ARITY:
                raise TypeError("Supply an exact adapter name/version pair")
            for value in pair:
                require_text(value=value, field="Adapter name/version")
        if len({pair[0] for pair in versions}) != len(versions):
            raise ValueError("Choose one reported version per adapter")
        object.__setattr__(self, "supported_capabilities", capabilities)
        object.__setattr__(self, "adapter_versions", tuple(sorted(versions)))


@dataclass(frozen=True, kw_only=True)
class ProjectionFinding:
    """One explained representation and its exact consumer responsibilities."""

    location: ProjectionLocation
    feature: ProjectionFeature
    representation: RepresentationSupport
    validation: ValidationResponsibility
    explanation: MeaningText
    obligations: Sequence[ConsumerObligation] = ()
    next_steps: Sequence[ProjectionRemedy] = ()

    def __post_init__(self) -> None:
        """Bind host validation findings to explicit typed duties."""
        for value, kind, label in (
            (self.location, ProjectionLocation, "Finding location"),
            (self.feature, ProjectionFeature, "Finding feature"),
            (self.representation, RepresentationSupport, "Representation support"),
            (self.validation, ValidationResponsibility, "Validation responsibility"),
            (self.explanation, MeaningText, "Finding explanation"),
        ):
            require_exact(value=value, expected=kind, field=label)
        obligations = ProjectionMetadata(consumer_obligations=self.obligations).consumer_obligations
        if (self.validation is ValidationResponsibility.HOST) != bool(obligations):
            raise ValueError("Select typed obligations exactly when validation requires the host")
        object.__setattr__(self, "obligations", obligations)
        object.__setattr__(
            self,
            "next_steps",
            snapshot_sequence(
                items=self.next_steps,
                item_type=ProjectionRemedy,
                field="Projection remedies",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ProjectionAssessment:
    """A reproducible read-only explanation of a projection against an exact release."""

    model: ModelVersion
    request: ProjectionRequest
    availability: ProjectionAvailability
    mapping: MappingDescriptor | None
    findings: Sequence[ProjectionFinding]
    consumer_obligations: Sequence[ConsumerObligation]
    issues: Sequence[Issue]
    next_steps: Sequence[ProjectionRemedy]
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Freeze evidence and enforce complete analysis state."""
        require_exact(value=self.model, expected=ModelVersion, field="Assessment model")
        require_projection_request(request=self.request)
        if isinstance(self.request, JsonSchemaProjectionRequest) and not isinstance(
            self.request.root, PinnedDefinitionReference
        ):
            raise TypeError("Use the verified pinned root in the assessment")
        require_exact(
            value=self.availability, expected=ProjectionAvailability, field="Availability"
        )
        require_exact(value=self.content_hash, expected=ContentHash, field="Assessment hash")
        for name, items, expected in (
            ("findings", self.findings, ProjectionFinding),
            ("issues", self.issues, Issue),
            ("next_steps", self.next_steps, ProjectionRemedy),
        ):
            object.__setattr__(
                self, name, snapshot_sequence(items=items, item_type=expected, field=name)
            )
        duties = ProjectionMetadata(
            consumer_obligations=self.consumer_obligations
        ).consumer_obligations
        if duties != tuple(
            dict.fromkeys(item for row in self.findings for item in row.obligations)
        ):
            raise ValueError("Report the exact ordered union of finding obligations")
        object.__setattr__(self, "consumer_obligations", duties)
        if self.availability is ProjectionAvailability.AVAILABLE:
            require_exact(
                value=self.mapping, expected=MappingDescriptor, field="Mapping descriptor"
            )
        elif self.findings or self.consumer_obligations:
            raise ValueError("Report capability failures without a partial semantic analysis")

    @property
    def exportable(self) -> bool:
        """Return whether every selected required feature can be represented."""
        return (
            self.availability is ProjectionAvailability.AVAILABLE
            and all(
                finding.representation is not RepresentationSupport.UNSUPPORTED
                and finding.validation is not ValidationResponsibility.UNSUPPORTED
                for finding in self.findings
            )
            and all(issue.severity is not IssueSeverity.ERROR for issue in self.issues)
        )


class ProjectionBlockedError(UnsupportedCapabilityError):
    """The requested mapping did not produce an exportable assessment."""

    def __init__(self, *, assessment: ProjectionAssessment) -> None:
        """Keep the exact report for recovery or selection of a different target."""
        require_exact(
            value=assessment, expected=ProjectionAssessment, field="Projection assessment"
        )
        if assessment.exportable:
            raise ValueError("Use the failed projection report")
        self.assessment: ProjectionAssessment = assessment
        super().__init__(message="Inspect the projection findings and select a supported export.")


@dataclass(frozen=True, kw_only=True)
class UnitAnnotation:
    """Preserve a scoped reusable unit in a schema manifest."""

    source: PinnedDefinitionReference
    name: str
    display_name: str
    meaning: str
    body: UnitDefinition
    aliases: Sequence[str] = ()
    terminology: Terminology = field(default_factory=Terminology)
    version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        """Validate exact unit metadata and its version."""
        require_exact(value=self.source, expected=PinnedDefinitionReference, field="Unit source")
        require_exact(value=self.body, expected=UnitDefinition, field="Unit body")
        require_exact(value=self.terminology, expected=Terminology, field="Unit terminology")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Unit display name")
        require_text(value=self.meaning, field="Unit meaning")
        require_exact(value=self.version, expected=str, field="Unit annotation version")
        if self.version != "1":
            raise ValueError("Select a supported unit annotation version")
        object.__setattr__(
            self,
            "aliases",
            snapshot_sequence(items=self.aliases, item_type=str, field="Unit aliases"),
        )


@dataclass(frozen=True, kw_only=True)
class UnitBindingAnnotation:
    """Preserve the exact edge from a value-set member to a reusable unit."""

    source: PinnedDefinitionReference
    code: BusinessCode
    unit: PinnedDefinitionReference
    version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        """Require the exact member and both declared pins."""
        require_exact(value=self.source, expected=PinnedDefinitionReference, field="Value set")
        require_exact(value=self.code, expected=BusinessCode, field="Unit code")
        require_exact(value=self.unit, expected=PinnedDefinitionReference, field="Bound unit")
        require_exact(value=self.version, expected=str, field="Unit binding version")
        if self.version != "1":
            raise ValueError("Select a supported unit binding version")


@dataclass(frozen=True, kw_only=True)
class IdentityBinding:
    """A stable scoped IRI for a released definition or its typed local path."""

    definition: PinnedDefinitionReference
    term_iri: Iri
    local_path: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Capture the exact owning identity and local child path."""
        require_exact(
            value=self.definition, expected=PinnedDefinitionReference, field="Identity owner"
        )
        require_exact(value=self.term_iri, expected=Iri, field="Term IRI")
        object.__setattr__(
            self,
            "local_path",
            snapshot_sequence(
                items=self.local_path,
                item_type=str,
                field="Local term path",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class SemanticDocument:
    """One exact byte representation and its intended graph role."""

    model: ModelVersion
    role: SemanticGraphRole
    graph_iri: Iri
    syntax: RdfSyntax
    payload: bytes = field(repr=False)
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Verify transport identity separately from model and graph identities."""
        require_exact(value=self.model, expected=ModelVersion, field="Graph model")
        require_exact(value=self.role, expected=SemanticGraphRole, field="Graph role")
        require_exact(value=self.graph_iri, expected=Iri, field="Graph IRI")
        require_exact(value=self.syntax, expected=RdfSyntax, field="Graph syntax")
        require_exact(value=self.payload, expected=bytes, field="Graph bytes")
        if self.content_hash != hash_bytes(content=self.payload):
            raise ValueError("Use the exact digest of the serialized graph")


@dataclass(frozen=True, kw_only=True)
class SemanticOntologyDependency:
    """A formally adopted closure bound to its exact scoped model."""

    model: ModelVersion
    ontology: OntologyClosurePin

    def __post_init__(self) -> None:
        """Require exact model and closure pins."""
        require_exact(value=self.model, expected=ModelVersion, field="Ontology owner")
        require_exact(value=self.ontology, expected=OntologyClosurePin, field="Ontology dependency")


@dataclass(frozen=True, kw_only=True)
class SemanticProjection:
    """Complete mapped RDF roles and selected external source material."""

    model: ModelVersion
    base_iri: Iri
    mapping: MappingDescriptor
    documents: Sequence[SemanticDocument]
    identities: Sequence[IdentityBinding]
    dependencies: Sequence[ModelVersion]
    issues: Sequence[Issue]
    limitations: Sequence[str]
    ontologies: Sequence[OntologyClosure] = field(default=(), repr=False)
    consumer_obligations: Sequence[ConsumerObligation] = ()
    ontology_dependencies: Sequence[SemanticOntologyDependency] = ()

    def __post_init__(self) -> None:
        """Require distinct graph roles for the exact projection closure."""
        require_exact(value=self.model, expected=ModelVersion, field="Projection model")
        require_exact(value=self.mapping, expected=MappingDescriptor, field="Projection mapping")
        require_projection_base(value=self.base_iri)
        for name, items, expected in (
            ("documents", self.documents, SemanticDocument),
            ("identities", self.identities, IdentityBinding),
            ("dependencies", self.dependencies, ModelVersion),
            ("issues", self.issues, Issue),
            ("limitations", self.limitations, str),
            ("ontologies", self.ontologies, OntologyClosure),
            ("ontology_dependencies", self.ontology_dependencies, SemanticOntologyDependency),
        ):
            object.__setattr__(
                self, name, snapshot_sequence(items=items, item_type=expected, field=name)
            )
        metadata = ProjectionMetadata(consumer_obligations=self.consumer_obligations)
        object.__setattr__(self, "consumer_obligations", metadata.consumer_obligations)
        models = {self.model, *self.dependencies}
        roles = {(document.model, document.role) for document in self.documents}
        if roles != {(model, role) for model in models for role in SemanticGraphRole} or len(
            roles
        ) != len(self.documents):
            raise ValueError("Preserve the four graph roles for each exact projected release")
        if len({document.graph_iri for document in self.documents}) != len(self.documents):
            raise ValueError("Use a distinct IRI for each projected graph role")


@dataclass(frozen=True, kw_only=True)
class ValidationGraphs:
    """Deterministic unpublished metadata and separate validation shape roles."""

    candidate: CandidatePin
    mapping: MappingDescriptor
    model_metadata: Sequence[OntologyStatement]
    model_shapes: Sequence[OntologyStatement]
    instance_shapes: Sequence[OntologyStatement]
    locations: Sequence[tuple[Iri, Sequence[str | int]]]
    issues: Sequence[Issue] = ()
    asserted_ontologies: Sequence[Sequence[OntologyStatement]] | None = None
    adopted_ontologies: Sequence[OntologyClosure] = ()

    def __post_init__(self) -> None:
        """Capture the exact candidate graph and declared diagnostic paths."""
        require_exact(value=self.candidate, expected=CandidatePin, field="Candidate pin")
        require_exact(value=self.mapping, expected=MappingDescriptor, field="Mapping")
        for field_name in ("model_metadata", "model_shapes", "instance_shapes"):
            rows: Sequence[OntologyStatement] = (
                self.model_metadata
                if field_name == "model_metadata"
                else self.model_shapes
                if field_name == "model_shapes"
                else self.instance_shapes
            )
            object.__setattr__(
                self,
                field_name,
                snapshot_sequence(
                    items=rows,
                    item_type=OntologyStatement,
                    field=field_name,
                ),
            )
        if self.asserted_ontologies is not None:
            if not is_non_string_sequence(self.asserted_ontologies):
                raise TypeError("Supply a sequence of asserted ontology graphs")
            object.__setattr__(
                self,
                "asserted_ontologies",
                tuple(
                    snapshot_sequence(
                        items=rows, item_type=OntologyStatement, field="Ontology graph"
                    )
                    for rows in self.asserted_ontologies
                ),
            )
        object.__setattr__(
            self,
            "adopted_ontologies",
            snapshot_sequence(
                items=self.adopted_ontologies, item_type=OntologyClosure, field="Adopted ontologies"
            ),
        )
        if not is_non_string_sequence(self.locations):
            raise TypeError("Supply a sequence of exact diagnostic locations")
        captured: list[tuple[Iri, tuple[str | int, ...]]] = []
        for node, parts in self.locations:
            require_exact(value=node, expected=Iri, field="Diagnostic node")
            if not is_non_string_sequence(parts) or any(
                type(part) not in (str, int) for part in parts
            ):
                raise TypeError("Supply a sequence of diagnostic path segments")
            captured.append((node, tuple(parts)))
        if len({node for node, _ in captured}) != len(captured):
            raise ValueError("Bind each validation node to one stable diagnostic path")
        object.__setattr__(self, "locations", tuple(captured))
        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(
                items=self.issues,
                item_type=Issue,
                field="Shape compilation issues",
            ),
        )
