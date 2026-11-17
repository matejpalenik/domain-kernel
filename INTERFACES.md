# Domain Kernel — Proposed interfaces

[ARCHITECTURE.md](ARCHITECTURE.md) is the single source of truth for SDK purpose,
behavior and boundaries. This reference specifies the proposed Python records and
ports for that architecture; [SDK_REQUIREMENTS.md](SDK_REQUIREMENTS.md) gives usage
recipes. Most sketches remain proposed APIs; the foundational DK-001 value contracts
and identifiers are implemented. This is not an instruction to scaffold all modules
before proving a complete slice. SDK method parameters are keyword-only,
except implicit `self`/`cls` receivers. Concrete identifier value objects accept
their single value positionally or by keyword; examples use explicit keyword arguments.

The architecture's [flat public API](ARCHITECTURE.md#flat-public-api) is normative:
`Client`, `Project` and `Model` expose direct methods with explicit signatures.
Their protocols below contain the complete callable surface; no dynamic forwarding
or grouped-service properties are public API. Typed value attributes such as
`model.info`, `model.scope` and `case.definitions` remain available.

This file also specifies internal slice contracts. `Projects`, `Models`,
`ReferencePacks`, `Sources`, `SourceRevisions`, `EvidenceAccess`, `Definitions`,
`Review`, `Discovery`, `Reconciliation`, `ModelVersions` and `Publications` are
internal application-service protocols. Component `api` modules expose them across
slice boundaries; they are not consumer entry points or root public exports. The
public handle delegates each direct method to its corresponding use case with the
same arguments, result, async behavior and transactional guarantees. Comments on
those internal contracts specify the delegated behavior; they do not define an
alternative public API. Coordinated changes remain single atomic use cases.

Domain objects and pure domain policies own invariants and permitted transitions;
immutable snapshots are not editable aggregates. Application services supply captured
state and coordinate transactions; repositories persist effects and enforce storage
concurrency/uniqueness, without choosing review or publication outcomes. Domain tests
exercise these rules without databases, application services or optional adapters.

Review cases expose synchronous `same_as`, `narrower_than`, `broader_than`,
`related_to` and `distinct_from` decision factories. They record the reviewer's
judgment, return typed decisions rather than booleans, and perform no I/O or writes.
`MapToDefinition` and `MapToReference` remain the typed result/wire variants;
examples construct them through these case methods. Preview/submission remain
separate async model operations and revalidate current stored state. Case-local
effect helpers are private; callers use `model.preview_changes()` and `model.decide_review()`.

Persistence-facing public methods and internal application services are async,
including reads, previews, comparisons, review and publication. Await them with
either database adapter. Handle properties expose loaded snapshots without I/O;
builders, decision constructors, snapshot getters and in-memory codecs/projections
remain synchronous. Client construction and explicit configuration loading remain
synchronous startup operations and perform no database access.
`model.iter_review_cases()` is a synchronous lazy iterator factory: database reads
are awaited during async iteration, using the same bounded pages as `list_review_cases()`.

Backend examples use these direct methods in separate host worker/request actions,
without additional SDK job helpers. Workers return persisted identities; frontends
inspect run failures, page continuation and preview impact. Review submission keeps
the inspected case and chosen decision; reloading a latest case must not bypass its
version guard. Publication retrieval by the exact inspected immutable ID is safe;
caught blocked-preparation diagnostics do not authorize publication. Each durable
operation retains its own retry intent. These examples add no SDK signatures.

Persistence repository methods below are async. `UnitOfWorkFactory` remains a
synchronous factory returning an async resource context; entry acquires one session
and its typed adapters, without starting a business transaction. Composition injects
specific collaborators into an operation-scoped service. Services explicitly implement
application protocols and never retrieve repositories from a broad bundle.
`TransactionManager.begin()` returns an async context manager that commits on normal
exit and rolls back on failure before commit. The resource context closes resources
without committing again. Never share a session between concurrent operations or
hold a transaction across acquisition/inference. Materialize returned records/pages
before release. Cancellation and commit errors do not establish rollback: retain
resource ownership through cleanup and recover uncertain outcomes by durable identity.
SQLAlchemy rows/sessions stay in infrastructure; domain values and policies remain
synchronous and stdlib-only. Blocking storage/parser work still runs off the event
loop. SDK-authored protocol implementations use explicit inheritance and `@override`
where layering permits; domain policies may satisfy application ports structurally
without importing them.

Domain Kernel turns source evidence, human knowledge and reference definitions into
editable, reviewed, versioned business domain models with provenance. FDE Workbench,
ERP and Inframeld GraphRAG embed it independently. Application workflows, executable
invariants, instance extraction and graph population remain outside these contracts.

The editing contract uses revision/retirement proposals and new correction cases;
no approved object is mutated in place. `ReviewImpact` explains dependent re-review,
`ChangeSet` supports same-model and exact-baseline comparison, and portable qualified
references resolve only against materialized pinned dependencies. Reference packs are
curated immutable packages with standalone composition/validation/serialization.
Models default to no pack. A reviewed pack-change case can attach, replace or
explicitly remove the active workspace pin before publication or later;
coordinated content changes group existing cases into one atomic review decision.
`DomainModelBuilder` produces immutable plans for additions, direct edits and removals; explicit
submission creates ordinary coordinated review cases atomically. Standards adapters
project the same model and preserve import provenance; RDFLib/pySHACL/LinkML types
never cross the public/domain boundary. See architecture chapters 6–9 for normative
behavior, supported subsets, mappings and failures.

The [manufacturing walkthrough](ARCHITECTURE.md#manufacturing-walkthrough-from-pdfs-to-a-reviewed-model)
illustrates these boundaries: `Machine` and `WorkOrder` definitions form the domain
model graph; `Press-17`, `WO-482` and their facts are host-owned instance data. Typed
SDK records remain authoritative in SQLite or optional PostgreSQL, and the complete
portable contract is `DomainModelBundle`. Temporary RDF graphs and exported
`SemanticProjection`/`LinkmlProjection` values do not introduce another editable
workspace. Instance extraction, graph writes and generated-code activation are host
operations, not additional SDK interfaces.

Formal interoperability uses immutable `OntologyClosure` resources and typed original
term references. `SemanticLinkDefinition` and `OntologyModuleDefinition` pass through
normal review; parsing, reasoning and module extraction are optional application-owned
ports. `ModelComposition` and `ModelSlice` are read-only derived views. See the
architecture's [ontology-resource contract](ARCHITECTURE.md#original-ontology-terms-and-immutable-semantic-resources),
[capability contract](ARCHITECTURE.md#semantic-links-inheritance-and-reasoning-capabilities)
and [granularity guidance](ARCHITECTURE.md#domain-modules-enterprise-compositions-and-workflow-views).
OWL import cycles, SDK dependency cycles and LinkML imports follow distinct rules.

The architecture's [defaults and type conventions](ARCHITECTURE.md#defaults-and-python-type-conventions)
apply throughout: named `StrEnum` choices, distinct immutable resource IDs, fixed
`Literal` discriminators, and validated strings for open vocabularies. Public Python
inputs require declared types; boundary codecs explicitly decode wire strings.
Optional creation capabilities default to `None`, optional collections to empty;
edit fields use `UNSET` to preserve omitted content. Stored snapshots contain the full state. New shape/terminology/dependency/check contracts
use nominal value objects and closed unions; primitive payloads occur inside those
objects and in wire codecs, never as interchangeable public arguments. Required review intent and concurrency
guards never gain implicit defaults. Domain records remain stdlib-only.

Project/model naming follows the architecture's [naming contract](ARCHITECTURE.md#project-and-model-names):
creation accepts `display_name` and optional `name`, or `name` alone; stored records
contain both resolved strings. Lookup uses `name`. Duplicate names fail without
suffixing or implicit retrieval. IDs remain independent of both naming fields.

Sources use these naming rules with project-local uniqueness and generated `SourceId`.
`ingest_source()` creates a logical source and its first immutable revision;
`ingest_source_revision(source_id=...)` appends to an existing source without renaming it.
`get_source()` accepts exactly one of `name` or `source_id`. Explicit inputs never
infer names from paths. Folder expansion applies the documented relative-path naming
rule once; IDs never derive from names or content digests. Revision hashes exclude
catalog naming metadata. Matching
idempotent retries replay the stored result, while a new duplicate creation fails.
Source records/reloads retain both names and the original ID; display-label changes
do not regenerate names/IDs. See [source naming](ARCHITECTURE.md#source-names-and-revisions).

Model creation also requires a non-blank `description`, preserved in `ModelInfo`,
interpretation context and published snapshots. It describes the model's business
area, intended use and boundaries. Definitions have `meaning` for their semantics
and specific qualifications, with no copied description or `scope_text` override.
Statement `context`, and exclusion and review-question scope text, retain their separate meanings.

Model-owned definitions follow the architecture's [definition naming contract](ARCHITECTURE.md#definition-names-and-lookups):
resolved `display_name` and stable `name` are stored separately from the generated ID.
Names are unique across local definition kinds; removed identities retain their names.
Discovery occurrences may share labels before review resolves catalog identity/name.
`get_concept()` exposes `Concept`, an immutable `Definition[ConceptDefinition]`
specialization with direct attribute/key getters and properties; relationship lookup
returns `Definition[RelationshipDefinition]`; `get_process()` returns
`Process` with direct child getters/properties and async persistence lookup.
`get_unit()` returns
`Definition[UnitDefinition]` by exactly one name or `unit_id`. Generic lookup exposes only the common
definition surface. The unparameterized record defaults to the full body union. Definition discriminators
use fixed `Literal[DefinitionKind.…]` members with unchanged string wire values.

`DomainModelBundle.get_concept()` applies the same exact name/ID lookup to the
bundle's local active or removed definitions synchronously, without I/O or a
historical revision selector. JSON Schema requests accept inspected concept or
structured-value definitions; assessment/export verify them against active bundle
content before normalizing to pinned references. Dependency roots retain explicit pins.

The SDK-wide collection contract covers methods, factories, record constructors and
configuration. `Sequence[T]` accepts lists or tuples, with examples using lists;
reject scalar strings/bytes, sets and one-shot iterators as collection containers.
Validate and immediately snapshot every collection into a tuple, recursively for
nested collection sequences. Stored record fields annotated `Sequence[T]` expose a
read-only interface and always contain tuples at runtime. Frozen dataclass
`__post_init__`, explicit constructors and configuration validators must enforce
this; `frozen=True` alone is insufficient. Returned tuple annotations and `()`
defaults remain appropriate; fixed-position tuples such as `(output_id, value)`
pairs keep their declared structure. Never retain a caller-owned mutable list.

Process parts (roles, activities, events, flows, gateways and conditions) generate
nominal IDs and resolve display_name/name. Names are unique across child kinds in
one process, independently of other processes and model-level definition names.
Immutable records accept direct objects, normalize stored edges to IDs/pins and
retain runtime-only inspected snapshots for builder validation. No implicit child
insertion or I/O. Condition input symbols and decision input/output keys retain
their separate string contracts. Process is a typed definition view, not a runtime job.

Attribute/key constructors generate their own IDs and resolve display_name/name.
Names are unique in the owning definition's attribute or key collection; duplicate
attachment raises `AttributeAlreadyExistsError` or `KeyAlreadyExistsError`.
Edits and codecs preserve IDs/names. Child edits belong to the owning concept's
revision and review lifecycle, not independent mutable child records.

Where exposed, `idempotency_key: str | None = None` remains optional. Resolve None to
a fresh opaque key once at the application-command boundary, reuse it for internal
retries/checkpoints, and leave caller-owned inputs unchanged. Never infer invocation
identity from content hashes, names or canonical request hashes; those validate inputs,
not whether a caller intends a retry. Separate unkeyed calls express new invocation
intent, subject to existing business guards and immutable artifact identity/reuse.
Stable caller keys enable cross-call/
worker replay, including a lost response; the host retains them before the first attempt.
Preserve documented exceptions: propose_plan defaults to plan.id, and generated
manifest-child inputs retain their stored keys. Retrieval/resumption by a known run ID
continues that run; a newly generated resume-command key is not a new discovery run.

Every durable public command and its delegated application service requires a non-blank
keyword-only `actor`. Pure helpers/readers/builders create no audit entries; author
metadata on returned values remains separate. See the architecture's
[durable-action audit contract](ARCHITECTURE.md#durable-action-audit) for mandatory
coverage, transaction boundaries, grouped effects and external-write recovery. Actor
identity/authority is host-verified and participates in canonical request hashing.
Internal persistence receives complete attributed records through its coordinator,
not a second unrelated actor parameter. Long-running work persists attribution and
parent links before dispatch; retries and resumption preserve earlier audit records.

Concrete identifier types are defined in the domain that owns the identity. The
shared module contains only the opaque base and values used across domains. Each
concrete identifier has its own module, is a frozen dataclass, and accepts its
single value positionally or by keyword. Dataclass equality remains class-sensitive;
valid spelling does not prove resource existence, scope, revision, or authority.

```python
# src/domain_kernel/shared/identifiers/opaque_identifier.py
from dataclasses import dataclass


@dataclass(frozen=True)
class OpaqueIdentifier:
    value: str

    def __post_init__(self) -> None: ...

    # Require exact str, nonempty, and no surrounding whitespace.
```

```python
# src/domain_kernel/modeling/domain/identifiers/definition_id.py
from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class DefinitionId(OpaqueIdentifier):
    """Stable identity for a company model definition."""
```

| Owner | Identifier types |
|---|---|
| `shared` | `AuditId`, `ContentHash`, `OpaqueIdentifier`, `PageCursor`, `PersonId` |
| `projects` | `ProjectId` |
| `modeling` | `AttributeId`, `DefinitionId`, `KeyId`, `ModelId`, `RoleId`, `ActivityId`, `EventId`, `GatewayId`, `FlowId`, `ConditionId` |
| `review` | `ApprovalId`, `ChangePlanId`, `DecisionId`, `ProposalId`, `ReviewCaseId` |
| `discovery` | `CandidateId`, `DiscoveryDraftId`, `DiscoveryRunId`, `ObligationId`, `QuestionId`, `ValidationReportId` |
| `reconciliation` | `AlignmentId`, `AlignmentSuggestionId`, `MappingId` |
| `sources` | `EvidenceId`, `SourceId`, `SourceRevisionId`, `SourceManifestId` |
| `reference_packs` | `PatternId`, `ReferenceDefinitionId` |
| `publication` | `BundleId`, `PublicationId` |

`ContentHash` and `SourceRevisionId` also require the exact `sha256:<64 lowercase
hex>` spelling. `AttributeId` rejects reserved `@id`, `@type`, and `rel:` spellings.
`PageCursor` is opaque and bound by the repository to its scope/filter/order query.
All concrete ID types are re-exported from `domain_kernel` for consumer use.

Each implemented enum has its own module under its owner's `enums/` directory. For
example, `IssueSeverity` lives in `shared/enums/issue_severity.py`, definition
lifecycle choices live in `modeling/domain/enums/`, and review choices live in
`review/domain/enums/`. The wider enum inventory below remains a proposal; future
enum types will live with their owning domain and each will have its own module.

```python
# Proposed enum inventory; DK-001 choices are implemented in their owning domains.
from __future__ import annotations

from enum import StrEnum, unique
from typing import Literal

# Python APIs use enum members. Wire/config loaders explicitly decode recognized string values.
# Values are spelled out and stable; never use auto() or accept unknown values silently.


@unique
class StatementForm(StrEnum):
    QUOTATION = "quotation"
    SUMMARY = "summary"


@unique
class StatementIntent(StrEnum):
    OBSERVATION = "observation"
    PROPOSAL = "proposal"
    ASSERTION = "assertion"


@unique
class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@unique
class DataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    REFERENCE = "reference"


@unique
class MappingRelation(StrEnum):
    EQUIVALENT = "equivalent"
    NARROWER = "narrower"
    BROADER = "broader"
    RELATED = "related"
    DISTINCT = "distinct"


@unique
class ConstraintTarget(StrEnum):
    MODEL = "model"
    INSTANCE = "instance"


@unique
class RdfSyntax(StrEnum):
    TURTLE = "turtle"
    JSONLD = "jsonld"


@unique
class LinkmlSyntax(StrEnum):
    YAML = "yaml"
    JSON = "json"


@unique
class SemanticGraphRole(StrEnum):
    ONTOLOGY = "ontology"
    MODEL_METADATA = "model_metadata"
    MODEL_SHAPES = "model_shapes"
    INSTANCE_SHAPES = "instance_shapes"


@unique
class ConstraintLanguage(StrEnum):
    TEXT = "text"
    JSON_SCHEMA = "json_schema"
    SHACL = "shacl"


@unique
class EventKind(StrEnum):
    START = "start"
    END = "end"
    INTERMEDIATE = "intermediate"
    EXCEPTION = "exception"


@unique
class GatewayKind(StrEnum):
    EXCLUSIVE = "exclusive"
    PARALLEL = "parallel"


@unique
class GatewayDirection(StrEnum):
    SPLIT = "split"
    JOIN = "join"


@unique
class FlowKind(StrEnum):
    NORMAL = "normal"
    CONDITIONAL = "conditional"
    DEFAULT = "default"
    EXCEPTION = "exception"


@unique
class HitPolicy(StrEnum):
    UNIQUE = "unique"
    FIRST = "first"
    COLLECT = "collect"


@unique
class DefinitionKind(StrEnum):
    CONCEPT = "concept"
    RELATIONSHIP = "relationship"
    PROCESS = "process"
    BUSINESS_DECISION = "business_decision"
    RULE = "rule"
    SEMANTIC_LINK = "semantic_link"
    ONTOLOGY_MODULE = "ontology_module"
    VALUE_SET = "value_set"
    UNIT = "unit"
    STRUCTURED_VALUE = "structured_value"
    ACCEPTANCE_CHECK = "acceptance_check"


@unique
class DefinitionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RETIRED = "retired"


@unique
class DefinitionOrigin(StrEnum):
    COMPANY = "company"
    REFERENCE_PACK_ADAPTATION = "reference_pack_adaptation"
    SCHEMA_IMPORT = "schema_import"
    LOCAL_EXTENSION = "local_extension"
    BASELINE = "baseline"


@unique
class EvidenceBasis(StrEnum):
    DOCUMENTED = "documented"
    DATA_INFERENCE = "data_inference"
    HYPOTHESIS = "hypothesis"
    STATEMENT = "statement"


@unique
class DefinitionChangeKind(StrEnum):
    ADD = "add"
    EDIT = "edit"
    RETIRE = "retire"
    REMOVE = "remove"
    MERGE = "merge"
    RELATE = "relate"
    SEPARATE = "separate"
    REUSE = "reuse"


@unique
class SourceDisposition(StrEnum):
    MAPPED = "mapped"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"


@unique
class ReferenceDispositionKind(StrEnum):
    MAPPED = "mapped"
    LOCAL_EXTENSION = "local_extension"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"


@unique
class Compatibility(StrEnum):
    INITIAL = "initial"
    COMPATIBLE = "compatible"
    BREAKING = "breaking"
    UNDETERMINED = "undetermined"


@unique
class ComparisonKind(StrEnum):
    PROPOSAL = "proposal"
    REVISION = "revision"
    BASELINE = "baseline"
    INITIAL = "initial"


@unique
class ConfirmationMethod(StrEnum):
    RECORDED = "recorded"
    AUTHENTICATED = "authenticated"


@unique
class OntologyFormat(StrEnum):
    TURTLE = "turtle"
    RDFXML = "rdfxml"
    JSONLD = "jsonld"
    NTRIPLES = "ntriples"


@unique
class RunStatus(StrEnum):
    INGESTING = "ingesting"
    EXTRACTING = "extracting"
    RECONCILING = "reconciling"
    NEEDS_REVIEW = "needs_review"
    READY_TO_PREPARE = "ready_to_prepare"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@unique
class AlignmentLayer(StrEnum):
    SOURCE_TO_MODEL = "source_to_model"
    MODEL_TO_REFERENCE = "model_to_reference"


@unique
class AlignmentStatus(StrEnum):
    PROPOSED = "proposed"
    PREPARED = "prepared"


@unique
class ReviewActionKind(StrEnum):
    ACCEPT = "accept"
    EDIT_DEFINITION = "edit_definition"
    REJECT = "reject"
    MAP_TO_DEFINITION = "map_to_definition"
    MAP_TO_REFERENCE = "map_to_reference"
    LOCAL_EXTENSION = "local_extension"
    EXCLUDE = "exclude"
    DEFER = "defer"
    KEEP_NONBLOCKING_QUESTION = "keep_nonblocking_question"
    ANSWER_QUESTION = "answer_question"
    CONFIRM_STATEMENT = "confirm_statement"


@unique
class CaseKind(StrEnum):
    PROPOSAL = "proposal"
    DEFINITION_REVISION = "definition_revision"
    DEFINITION_RETIREMENT = "definition_retirement"
    DEFINITION_RESTORATION = "definition_restoration"
    SOURCE_ALIGNMENT = "source_alignment"
    REFERENCE_ALIGNMENT = "reference_alignment"
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    REFERENCE_PACK_CHANGE = "reference_pack_change"
    CHANGE_SET = "change_set"


@unique
class CaseStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    REVIEWED_NONBLOCKING = "reviewed_nonblocking"
    SUPERSEDED = "superseded"


@unique
class RequirementKind(StrEnum):
    CORE = "core"
    EVIDENCE = "evidence"
    REFERENCE_PACK = "reference_pack"


@unique
class QuestionDisposition(StrEnum):
    UNRESOLVED = "unresolved"
    ANSWERED = "answered"
    REVIEWED_NONBLOCKING = "reviewed_nonblocking"
    SUPERSEDED = "superseded"


@unique
class ReferenceAssetKind(StrEnum):
    ONTOLOGY = "ontology"
    DEFINITIONS = "definitions"
    PATTERNS = "patterns"
    REFERENCE_PACK = "reference_pack"


@unique
class ObligationKind(StrEnum):
    COVERAGE = "coverage"
    DEFINITION = "definition"
    ALIGNMENT = "alignment"
    PROCESS = "process"
    DECISION = "decision"
    CONFIRMATION = "confirmation"
    SEMANTIC = "semantic"


@unique
class PackMaturity(StrEnum):
    EXPERIMENTAL = "experimental"
    REVIEWED = "reviewed"


@unique
class ModelKind(StrEnum):
    OBSERVED = "observed"
    PROPOSED = "proposed"


@unique
class ExportFormat(StrEnum):
    JSON = "json"
    JSON_SCHEMA = "json_schema"
    JSONLD = "jsonld"
    TURTLE = "turtle"


@unique
class InferredColumnType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    MIXED = "mixed"
    UNKNOWN = "unknown"
    NULL = "null"


type ScalarDataType = Literal[
    DataType.STRING,
    DataType.INTEGER,
    DataType.DECIMAL,
    DataType.BOOLEAN,
    DataType.DATE,
    DataType.DATETIME,
]
```

```python
# src/domain_kernel/_shared/domain/ontology.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Proposed signatures only; not executable implementations.


@dataclass(frozen=True, kw_only=True)
class Iri:
    value: str
    kind: Literal["iri"] = "iri"


@dataclass(frozen=True, kw_only=True)
class BlankNode:
    id: str
    kind: Literal["blank_node"] = "blank_node"


@dataclass(frozen=True, kw_only=True)
class RdfLiteral:
    value: str
    datatype: Iri | None = None
    language: str | None = None
    kind: Literal["literal"] = "literal"


@dataclass(frozen=True, kw_only=True)
class OntologyStatement:
    subject: Iri | BlankNode
    predicate: Iri
    object: Iri | BlankNode | RdfLiteral
    graph: Iri | BlankNode | None = None
```

```python
# src/domain_kernel/_shared/domain/ontology_assets.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from enum import StrEnum, unique

from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel._shared.domain.ontology import BlankNode, Iri, OntologyStatement


@unique
class OntologySyntax(StrEnum):
    TURTLE = "turtle"
    RDFXML = "rdfxml"
    JSONLD = "jsonld"
    NTRIPLES = "ntriples"
    TRIG = "trig"
    NQUADS = "nquads"
    OWLXML = "owlxml"
    FUNCTIONAL = "functional"
    MANCHESTER = "manchester"


@unique
class OntologyEntityKind(StrEnum):
    CLASS = "class"
    OBJECT_PROPERTY = "object_property"
    DATA_PROPERTY = "data_property"
    ANNOTATION_PROPERTY = "annotation_property"
    RDF_PROPERTY = "rdf_property"
    DATATYPE = "datatype"
    INDIVIDUAL = "individual"
    SKOS_CONCEPT = "skos_concept"


@unique
class SemanticRelation(StrEnum):
    SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
    SUBPROPERTY_OF = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"
    EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"
    EQUIVALENT_PROPERTY = "http://www.w3.org/2002/07/owl#equivalentProperty"
    DISJOINT_WITH = "http://www.w3.org/2002/07/owl#disjointWith"
    INVERSE_OF = "http://www.w3.org/2002/07/owl#inverseOf"
    SAME_AS = "http://www.w3.org/2002/07/owl#sameAs"
    DIFFERENT_FROM = "http://www.w3.org/2002/07/owl#differentFrom"
    EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"
    CLOSE_MATCH = "http://www.w3.org/2004/02/skos/core#closeMatch"
    BROAD_MATCH = "http://www.w3.org/2004/02/skos/core#broadMatch"
    NARROW_MATCH = "http://www.w3.org/2004/02/skos/core#narrowMatch"
    RELATED_MATCH = "http://www.w3.org/2004/02/skos/core#relatedMatch"
    SEE_ALSO = "http://www.w3.org/2000/01/rdf-schema#seeAlso"
    IS_DEFINED_BY = "http://www.w3.org/2000/01/rdf-schema#isDefinedBy"


@dataclass(frozen=True, kw_only=True)
class OntologyDocumentPin:
    document_iri: Iri
    content_hash: ContentHash
    ontology_iri: Iri | None = None
    version_iri: Iri | None = None
    ontology_graph: Iri | BlankNode | None = None  # None selects only the default graph.
    # Exact-byte identity; parsed headers must match. Version IRI requires ontology IRI.


@dataclass(frozen=True, kw_only=True)
class OntologyTermReference:
    source: OntologyDocumentPin
    term_iri: Iri
    entity_kind: OntologyEntityKind
    # Source must be materialized; kind is verified, not guessed from the label.
    # The same IRI may occur with different kinds (punning); neither identity nor kind is rewritten.


@dataclass(frozen=True, kw_only=True)
class OntologyDocument:
    pin: OntologyDocumentPin
    syntax: OntologySyntax
    payload: bytes


@dataclass(frozen=True, kw_only=True)
class ParsedOntology:
    document: OntologyDocument
    parser_id: str
    parser_version: str
    statements: Sequence[OntologyStatement]
    terms: Sequence[OntologyTermReference]
    import_iris: Sequence[Iri] = ()
    context_iris: Sequence[Iri] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Preserve the complete RDF 1.1 dataset; headers/imports/terms describe the selected ontology_graph.
    # Other named graphs remain available as preserved content; never implicitly union them.
    # OWL structural syntaxes use the standard OWL-to-RDF mapping, never a reduced invented schema.


@dataclass(frozen=True, kw_only=True)
class OntologyImportBinding:
    source: OntologyDocumentPin
    import_iri: Iri
    target: OntologyDocumentPin


@dataclass(frozen=True, kw_only=True)
class OntologyContextBinding:
    source: OntologyDocumentPin
    context_iri: Iri
    target: OntologyDocumentPin


@dataclass(frozen=True, kw_only=True)
class OntologyClosure:
    root: OntologyDocumentPin
    documents: Sequence[ParsedOntology]
    imports: Sequence[OntologyImportBinding]
    contexts: Sequence[OntologyContextBinding]
    resources: Sequence[OntologyDocument]  # Used supplied contexts; never live locators.
    content_hash: ContentHash

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Hash canonical typed content: exact byte pins, parsed statements, bindings and parser identity.
    # This is a representation digest, not graph-isomorphism or proof of parser correctness.
    # Complete closure, finite traversal of legal OWL import cycles; verify all bytes/headers/pins.
    # No missing import/context, ambiguous requested alias or silently dropped graph.
    # Explicit distinct version imports can coexist; a single IRI/hash binding cannot conflict.


@dataclass(frozen=True, kw_only=True)
class OntologyClosurePin:
    root: OntologyDocumentPin
    content_hash: ContentHash


@dataclass(frozen=True, kw_only=True)
class OntologyLimits:
    max_bytes: int = 64 * 1024 * 1024
    max_documents: int = 256
    max_statements: int = 1_000_000
    timeout_ms: int = 60_000
    # Positive finite bounds; apply before expansion and across complete closure/output.
```

```python
# Proposed full contract inventory; implementation follows each type's domain owner.
# DK-001's cross-domain subset is implemented in src/domain_kernel/shared/contracts.py.
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId

from domain_kernel._shared.domain.ontology_assets import OntologyClosurePin

from domain_kernel._shared.domain.enums import (
    IssueSeverity,
    SemanticGraphRole,
    StatementForm,
    StatementIntent,
)

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId


from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from domain_kernel._shared.domain.ontology import Iri, OntologyStatement


# Proposed signatures. Source-owned records below are future contracts, not shared state.
@dataclass(frozen=True, kw_only=True)
class ModelScope:
    project_id: ProjectId
    model_id: ModelId


@dataclass(frozen=True, kw_only=True)
class FileOrigin:
    reader: str
    provider_scope: str
    location: str
    provider_version: str | None
    acquired_at: datetime
    kind: Literal["file"] = "file"


@dataclass(frozen=True, kw_only=True)
class Person:
    id: PersonId
    name: str
    role: str


@dataclass(frozen=True, kw_only=True)
class StatementOrigin:
    speaker: Person
    recorded_by: str  # Resolved non-blank recorder; omitted input defaults to the ingestion actor.
    stated_at: datetime | None  # Original timezone-aware statement time; None means unknown.
    recorded_at: datetime  # SDK ingestion time; never substitutes for stated_at.
    context: str  # Required non-blank applicability context, independent of model description.
    form: StatementForm
    intent: StatementIntent
    payload_schema_version: Literal[1] = 1
    kind: Literal["statement"] = "statement"


@dataclass(frozen=True, kw_only=True)
class ParsedSourceOrigin:
    provider: str
    document_id: str
    document_revision: str
    captured_at: datetime
    claimed_original_digest: ContentHash | None = None  # Host assertion, never verified file bytes.
    kind: Literal["supplied"] = (
        "supplied"  # Stable serialized tag; public type names do not change wire data.
    )


type Origin = FileOrigin | StatementOrigin | ParsedSourceOrigin


@dataclass(frozen=True, kw_only=True)
class SourceRevision:
    project_id: ProjectId  # Raw evidence is shared by models in this project.
    source_id: SourceId
    revision_id: SourceRevisionId  # sha256:<64 hex>; basis follows origin.kind.
    # file: all original bytes; statement/supplied: versioned canonical captured payload.
    # Never use an ETag/provider version as the digest; processing fingerprints are separate.
    byte_length: int
    origin: Origin


@dataclass(frozen=True, kw_only=True)
class CellRange:
    sheet: str
    cells: str
    kind: Literal["cells"] = "cells"


@dataclass(frozen=True, kw_only=True)
class DocumentSpan:
    page: int | None = None
    section: str | None = None
    start: int
    end: int
    kind: Literal["document_span"] = "document_span"


@dataclass(frozen=True, kw_only=True)
class StatementSpan:
    start: int
    end: int
    kind: Literal["statement_span"] = "statement_span"


@dataclass(frozen=True, kw_only=True)
class OntologyLocation:
    statement: OntologyStatement
    kind: Literal["ontology_location"] = "ontology_location"


@dataclass(frozen=True, kw_only=True)
class ExternalLocation:
    key: str  # Stable host locator, never an implicit URL to dereference.
    kind: Literal["external"] = "external"


type EvidenceLocator = (
    CellRange | DocumentSpan | StatementSpan | OntologyLocation | ExternalLocation
)


@dataclass(frozen=True, kw_only=True)
class SchemaOrigin:
    schema_iri: Iri
    element_iri: Iri | None
    element_path: Sequence[str | int]
    source_hash: ContentHash  # Exact supplied schema bytes, not a verified business assertion.
    dependency_hashes: Sequence[ContentHash]
    mapping_version: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Provenance only; never dereference this IRI or infer local identity/approval from it.


@dataclass(frozen=True, kw_only=True)
class ProcessingRecord:
    source: SourceRevision
    fingerprint: str
    parser_id: str
    parser_version: str
    provider_model_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class Evidence:
    id: EvidenceId
    source: SourceRevision
    locator: EvidenceLocator
    processing: ProcessingRecord  # Citation only; content loading is explicit.


@dataclass(frozen=True, kw_only=True)
class ReferencePackPin:
    key: str
    version: str
    content_hash: ContentHash


@dataclass(frozen=True, kw_only=True)
class ModelVersion:
    scope: ModelScope
    version: str
    content_hash: ContentHash


@dataclass(frozen=True, kw_only=True)
class CandidatePin:
    scope: ModelScope
    candidate_id: CandidateId
    content_hash: ContentHash


type SnapshotReference = ModelVersion | CandidatePin


@dataclass(frozen=True, kw_only=True)
class PinnedDefinitionReference:
    model: ModelVersion
    definition_id: DefinitionId
    definition_revision: int
    kind: Literal["pinned_definition"] = "pinned_definition"


# Bare DefinitionId values reference definitions in the current model scope.
type CompanyDefinitionReference = DefinitionId | PinnedDefinitionReference
type DefinitionReference = CompanyDefinitionReference | ReferenceDefinitionId
# Company bodies accept DefinitionId/pinned model refs; pack bodies accept ReferenceDefinitionId.
# Validators enforce that context; an ID type never establishes scope or publication authority.


@dataclass(frozen=True, kw_only=True)
class KeyEnforcementObligation:
    owner: PinnedDefinitionReference
    key: KeyId
    kind: Literal["key_enforcement"] = "key_enforcement"


@dataclass(frozen=True, kw_only=True)
class ReferenceTargetObligation:
    owner: PinnedDefinitionReference
    attribute: AttributeId
    kind: Literal["reference_target"] = "reference_target"


@dataclass(frozen=True, kw_only=True)
class RelationshipEnforcementObligation:
    relationship: PinnedDefinitionReference
    kind: Literal["relationship_enforcement"] = "relationship_enforcement"


@dataclass(frozen=True, kw_only=True)
class CollectionSemanticsObligation:
    # Emit where representation preserves the shape but target validation cannot fully enforce it.
    owner: PinnedDefinitionReference
    attribute: AttributeId
    kind: Literal["collection_semantics"] = "collection_semantics"
    # Bound attribute carries required/collection/min_items/max_items; no duplicated constraint state.
    # Host checks presence before normalization, then item bounds and typed equality when present.
    # Never silently deduplicate. An obligation cannot recover missing-vs-empty information lost by a mapping.


type ConsumerObligation = (
    KeyEnforcementObligation
    | ReferenceTargetObligation
    | RelationshipEnforcementObligation
    | CollectionSemanticsObligation
)


@dataclass(frozen=True, kw_only=True)
class SemanticArtifactMetadata:
    model: ModelVersion
    graph_iri: Iri
    role: SemanticGraphRole
    mapping_version: str
    ontology_dependencies: Sequence[OntologyClosurePin] = ()  # Exact adopted formal closures.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Keeps graph placement and source identity when exporting just one semantic document.


@dataclass(frozen=True, kw_only=True)
class Artifact:
    project_id: ProjectId
    store: str
    key: str
    content_hash: ContentHash
    model_id: ModelId | None = None  # None for project-scoped original copies.
    provider_version: str | None = None
    projection_limits: Sequence[str] = ()
    semantic: SemanticArtifactMetadata | None = None
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Issue:
    code: str
    path: Sequence[str | int]
    message: str  # Sanitized; no secrets or raw provider exception context.
    severity: IssueSeverity = IssueSeverity.ERROR

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Page[T]:
    items: Sequence[T]
    next_cursor: PageCursor | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ProjectInfo:
    id: ProjectId
    name: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class ProcessingLimits:
    max_source_bytes: int
    max_concurrent_sources: int
    max_expanded_bytes: int
    max_pages: int


@dataclass(frozen=True, kw_only=True)
class ExtractionProvenance:
    processing_fingerprint: str
    extractor_id: str
    extractor_version: str
    provider_model_id: str | None = None
```

```python
# src/domain_kernel/_shared/domain/model_values.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from enum import StrEnum, unique


@dataclass(frozen=True, kw_only=True)
class _TextValue:
    value: str

    def __post_init__(self) -> None: ...

    # Exact nonempty Unicode string; reject surrounding whitespace, never silently normalize.
    # Subclasses are nominal, class-sensitive value objects; primitive storage is private to the VO contract.


@dataclass(frozen=True, kw_only=True)
class BusinessCode(_TextValue):
    pass  # Stable, case-sensitive identity within a value set; changing a label never changes a code.


@dataclass(frozen=True, kw_only=True)
class LabelText(_TextValue):
    pass


@dataclass(frozen=True, kw_only=True)
class MeaningText(_TextValue):
    pass


@dataclass(frozen=True, kw_only=True)
class LanguageTag(_TextValue):
    def __post_init__(self) -> None: ...

    # Well-formed BCP 47; canonical ASCII lowercase for comparison/wire, no registry/network lookup.
    # Well-formedness is not a claim that an arbitrary subtag is registered or that text is translated.


@dataclass(frozen=True, kw_only=True)
class Count:
    value: int

    def __post_init__(self) -> None: ...  # Exact int >= 0, reject bool.


@dataclass(frozen=True, kw_only=True)
class DecimalPrecision:
    value: int

    def __post_init__(self) -> None: ...  # Exact int >= 1, reject bool.


@dataclass(frozen=True, kw_only=True)
class DecimalScale:
    value: int

    def __post_init__(self) -> None: ...  # Exact int >= 0, reject bool.


@unique
class CollectionKind(StrEnum):
    SINGLE = "single"
    SET = "set"
    LIST = "list"


@unique
class Nullability(StrEnum):
    FORBIDDEN = "forbidden"
    ALLOWED = "allowed"


@unique
class ValueSetMembership(StrEnum):
    CLOSED = "closed"
    OPEN = "open"


@unique
class LabelRole(StrEnum):
    PREFERRED = "preferred"
    ALTERNATIVE = "alternative"
    HIDDEN = "hidden"


@dataclass(frozen=True, kw_only=True)
class LocalizedLabel:
    text: LabelText
    language: LanguageTag
    role: LabelRole = LabelRole.PREFERRED


@dataclass(frozen=True, kw_only=True)
class LocalizedDescription:
    text: MeaningText
    language: LanguageTag


@dataclass(frozen=True, kw_only=True)
class Terminology:
    labels: Sequence[LocalizedLabel] = ()
    descriptions: Sequence[LocalizedDescription] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # At most one preferred label/description per language. Label roles disjoint for the same text/tag.
    # Empty means no localized metadata; never infer a language for display labels/meaning/aliases.


@dataclass(frozen=True, kw_only=True)
class CardinalityBounds:
    minimum: Count = Count(value=0)
    maximum: Count | None = Count(value=1)  # None is explicitly unbounded.

    def __post_init__(self) -> None: ...  # maximum >= minimum when finite.


@dataclass(frozen=True, kw_only=True)
class RelationshipCardinality:
    outgoing: CardinalityBounds
    incoming: CardinalityBounds

    @classmethod
    def one_to_one(cls) -> RelationshipCardinality: ...
    @classmethod
    def one_to_many(cls) -> RelationshipCardinality: ...
    @classmethod
    def many_to_one(cls) -> RelationshipCardinality: ...
    @classmethod
    def many_to_many(cls) -> RelationshipCardinality: ...

    # Factories retain zero minima; ONE_TO_MANY has unbounded outgoing and max-one incoming.


@dataclass(frozen=True, kw_only=True)
class DecimalFacets:
    precision: DecimalPrecision | None = None
    scale: DecimalScale | None = None

    def __post_init__(
        self,
    ) -> None: ...  # Require at least one facet; scale <= precision when both supplied.

    # Maximum significant/fractional digits on the normalized decimal value; no implicit rounding.
```

```python
# src/domain_kernel/_shared/domain/data_shapes.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from typing import Literal
from domain_kernel._shared.domain.contracts import DefinitionReference
from domain_kernel._shared.domain.enums import ScalarDataType
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel._shared.domain.model_values import DecimalFacets
from domain_kernel._shared.domain.ontology_assets import OntologyTermReference


@dataclass(frozen=True, kw_only=True)
class ScalarValueType:
    data_type: ScalarDataType
    decimal: DecimalFacets | None = None  # Only for DECIMAL; other types reject it.
    kind: Literal["scalar"] = "scalar"


@dataclass(frozen=True, kw_only=True)
class ConceptReferenceType:
    concept: DefinitionReference
    kind: Literal["concept_reference"] = "concept_reference"


@dataclass(frozen=True, kw_only=True)
class ValueSetType:
    value_set: DefinitionReference
    kind: Literal["value_set"] = "value_set"


@dataclass(frozen=True, kw_only=True)
class StructuredValueType:
    structure: DefinitionReference
    kind: Literal["structured_value"] = "structured_value"


type AttributeType = ScalarValueType | ConceptReferenceType | ValueSetType | StructuredValueType


@dataclass(frozen=True, kw_only=True, init=False)
class KeyDefinition:
    id: KeyId
    name: str
    display_name: str
    attributes: tuple[AttributeId, ...]

    def __init__(
        self,
        *,
        attributes: Sequence[AttributeId],
        display_name: str | None = None,
        name: str | None = None,
    ) -> None: ...

    # Generate the ID once; resolve display_name/name using the shared naming contract.
    # Validate and copy attributes immediately; caller mutation cannot change this record.
    # Nonempty distinct direct fields of the owning concept; each required=True, SINGLE and non-null.
    # Scalar/value-set/reference fields only. Combination unique within the host's instance scope.
    # Owner attachment checks name/ID uniqueness. Codec/revision reconstruction preserves identity.
    # A site-local code uses (site_reference, code). This is not owl:hasKey or an entity merge rule.


@dataclass(frozen=True, kw_only=True)
class QuantityBinding:
    magnitude: AttributeId
    unit: AttributeId
    quantity_kind: OntologyTermReference | None = None
    # On a StructuredValueDefinition: magnitude required non-null numeric SINGLE;
    # unit required non-null SINGLE closed ValueSetType. Inline units need no ontology reference.
    # None preserves this binding: the owning quantity definition supplies the local meaning.
    # Member.unit references resolve to UnitDefinition; their ontology bindings belong to that unit.
    # Supplied quantity-kind/unit terms must be INDIVIDUAL or SKOS_CONCEPT in materialized resources.
    # Pinned ontology identities describe meaning; dimensional checking/conversion is an optional adapter.
```

```python
# src/domain_kernel/_shared/domain/dependencies.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from domain_kernel._shared.domain.contracts import ModelVersion, PinnedDefinitionReference


@dataclass(frozen=True, kw_only=True)
class DependencyRemapping:
    before: PinnedDefinitionReference
    after: PinnedDefinitionReference
    # Exact identities/revisions in the old/new closures; no label matching or implicit redirects.


@dataclass(frozen=True, kw_only=True)
class DependencyChangeRequest:
    before: Sequence[ModelVersion]
    after: Sequence[
        ModelVersion
    ]  # Complete desired direct dependency set; [] explicitly removes all.
    remappings: Sequence[DependencyRemapping] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Before must equal inspected ModelInfo.dependencies; after differs. Same-project verified DAG.
    # No duplicate source remapping; many-to-one remapping is explicit, never inferred equivalence.
```

```python
# src/domain_kernel/_shared/domain/acceptance.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Literal
from domain_kernel._shared.domain.contracts import DefinitionReference, Issue
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel._shared.domain.model_values import MeaningText
from domain_kernel._shared.domain.enums import DefinitionKind


@unique
class CheckRequirement(StrEnum):
    REQUIRED = "required"
    ADVISORY = "advisory"


@unique
class CheckOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True, kw_only=True)
class DistinctDefinitionsCheck:
    left: DefinitionReference
    right: DefinitionReference
    kind: Literal["distinct_definitions"] = "distinct_definitions"
    # Checks different resolved SDK identities only; does not prove OWL disjointness or business truth.


@dataclass(frozen=True, kw_only=True)
class QuantityRequiredCheck:
    structure: DefinitionReference
    kind: Literal["quantity_required"] = "quantity_required"
    # Checks a structurally valid QuantityBinding, including quantity_kind=None, on this structured value.


@dataclass(frozen=True, kw_only=True)
class ManualCriterion:
    kind: Literal["manual_criterion"] = "manual_criterion"
    # Always UNKNOWN in machine validation; authoring acceptance does not manufacture a PASS.


type AcceptancePredicate = DistinctDefinitionsCheck | QuantityRequiredCheck | ManualCriterion


@dataclass(frozen=True, kw_only=True)
class AcceptanceCheckDefinition:
    statement: MeaningText
    requirement: CheckRequirement
    predicate: AcceptancePredicate
    kind: Literal[DefinitionKind.ACCEPTANCE_CHECK] = DefinitionKind.ACCEPTANCE_CHECK
    # Normal definition lifecycle/evidence/review. Machine checks run on the exact candidate.
    # A required manual criterion blocks publication until reviewed replacement with executable criteria
    # or explicit reviewed reclassification to advisory; no implicit waiver or free-form query execution.


@dataclass(frozen=True, kw_only=True)
class AcceptanceCheckResult:
    definition_id: DefinitionId
    candidate_hash: ContentHash  # Resolves the exact check revision and all referenced definitions.
    outcome: CheckOutcome
    evaluator_fingerprint: ContentHash
    issues: Sequence[Issue] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Exactly one result per active local acceptance-check definition; dependency checks keep their own scope.
    # Results are validation outputs, excluded from their input candidate hash.
```

```python
# src/domain_kernel/_shared/domain/definitions.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel._shared.domain.model_values import (
    DecimalFacets,
    BusinessCode,
    LabelText,
    MeaningText,
    Terminology,
    CollectionKind,
    Count,
    Nullability,
    RelationshipCardinality,
    ValueSetMembership,
)
from domain_kernel._shared.domain.data_shapes import AttributeType, KeyDefinition, QuantityBinding
from domain_kernel._shared.domain.acceptance import AcceptanceCheckDefinition

from domain_kernel._shared.domain.enums import (
    ComparisonKind,
    Compatibility,
    ConstraintLanguage,
    ConstraintTarget,
    DataType,
    DefinitionChangeKind,
    DefinitionKind,
    DefinitionOrigin,
    DefinitionStatus,
    EventKind,
    EvidenceBasis,
    FlowKind,
    GatewayDirection,
    GatewayKind,
    HitPolicy,
    MappingRelation,
    ReferenceDispositionKind,
    ScalarDataType,
    SourceDisposition,
)

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId


from domain_kernel._shared.domain.ontology_assets import (
    OntologyClosure,
    OntologyEntityKind,
    OntologyTermReference,
    SemanticRelation,
)

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from domain_kernel._shared.domain.contracts import (
    DefinitionReference,
    Evidence,
    ExtractionProvenance,
    ModelScope,
    ModelVersion,
    ReferencePackPin,
    SnapshotReference,
    SchemaOrigin,
)


@dataclass(frozen=True, kw_only=True)
class DecisionValue:
    value: str | bool | int | Decimal | date | datetime

    # Exact native scalar; reject nonfinite decimals, naive datetimes and unsupported types.
    # Distinguish bool from int and datetime from date; do not coerce a numeric string.
    @property
    def data_type(self) -> ScalarDataType: ...  # Derived from value; cannot contradict it.


@dataclass(frozen=True, kw_only=True)
class ConstraintDefinition:
    id: str
    description: str
    language: ConstraintLanguage
    expression: str  # Inert definition; never evaluated as Python.
    target: ConstraintTarget = ConstraintTarget.MODEL
    evidence: Sequence[Evidence] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True, init=False)
class AttributeDefinition:
    id: AttributeId
    name: str
    display_name: str
    value_type: AttributeType
    required: bool = False
    collection: CollectionKind = CollectionKind.SINGLE
    min_items: Count | None = None
    max_items: Count | None = None
    nullability: Nullability = Nullability.FORBIDDEN
    constraints: tuple[ConstraintDefinition, ...] = ()
    terminology: Terminology = Terminology()

    def __init__(
        self,
        *,
        value_type: AttributeType,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> None: ...
    @classmethod
    def string(
        cls,
        *,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition: ...
    @classmethod
    def decimal(
        cls,
        *,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
        facets: DecimalFacets | None = None,
    ) -> AttributeDefinition: ...
    @classmethod
    def reference(
        cls,
        *,
        target: DefinitionReference,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition: ...
    @classmethod
    def value_set(
        cls,
        *,
        value_set: DefinitionReference,
        display_name: str | None = None,
        name: str | None = None,
        required: bool = False,
        collection: CollectionKind = CollectionKind.SINGLE,
        min_items: Count | None = None,
        max_items: Count | None = None,
        nullability: Nullability = Nullability.FORBIDDEN,
        constraints: Sequence[ConstraintDefinition] = (),
        terminology: Terminology | None = None,
    ) -> AttributeDefinition: ...

    # Generate one AttributeId at construction; optional name overrides the display-name slug.
    # Copy constraints immediately; terminology=None resolves to empty immutable metadata.
    # Owner attachment validates local name/ID uniqueness; names and IDs survive display edits.
    # Codec/revision reconstruction preserves IDs; public creation never accepts a caller-assigned ID.
    # required controls field presence independently of item bounds; require an exact bool.
    # SINGLE: min_items/max_items must be None; present value is scalar/reference/structured, never an array.
    # SET/LIST: min_items=None normalizes to Count(value=0); max_items=None is unbounded.
    # Store canonical counts on collections; reject finite max_items < min_items and raw int counts.
    # SET is unordered/distinct; LIST preserves order and duplicates. Both are non-null, including items.
    # Absent passes only if required=False. Bounds apply only when a collection is present.
    # required=True/min_items=0 permits present empty; required=False with a positive minimum permits absence and valid nonempty values, not empty collections.
    # SINGLE may be nullable independently of required; required does not imply a nonempty string.
    # No duplicate presence/bounds representation or primitive data_type/concept_id shortcuts.
    # Factories return this record with ScalarValueType(STRING/DECIMAL), ConceptReferenceType or ValueSetType.
    # value_set constructs ValueSetType(value_set=value_set); never creates, copies or looks up the set.
    # Reference targets retain typed IDs/pins, never inferred from names; builder captures inspected refs.


@dataclass(frozen=True, kw_only=True)
class ConceptDefinition:
    attributes: Sequence[AttributeDefinition] = ()
    keys: Sequence[KeyDefinition] = ()
    kind: Literal[DefinitionKind.CONCEPT] = DefinitionKind.CONCEPT

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class StructuredValueDefinition:
    attributes: Sequence[AttributeDefinition]
    quantity: QuantityBinding | None = None
    kind: Literal[DefinitionKind.STRUCTURED_VALUE] = DefinitionKind.STRUCTURED_VALUE

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Nonempty fields, no entity keys, no recursive embedding; concept references may be cyclic.


@dataclass(frozen=True, kw_only=True)
class UnitDefinition:
    symbol: str | None = None
    ontology_term: OntologyTermReference | None = None
    kind: Literal[DefinitionKind.UNIT] = DefinitionKind.UNIT

    def __post_init__(self) -> None: ...

    # Owning Definition supplies generated ID, name/display_name, meaning, aliases and terminology.
    # A supplied symbol is nonblank exact text, not an identifier or a globally unique code.
    # No external term is required. Supplied terms must resolve as INDIVIDUAL or SKOS_CONCEPT.
    # A provenance binding neither asserts owl:sameAs nor adopts the source ontology's axioms.


@dataclass(frozen=True, kw_only=True)
class ValueSetMember:
    code: BusinessCode
    label: LabelText
    meaning: MeaningText
    ontology_term: OntologyTermReference | None = None
    terminology: Terminology = Terminology()
    unit: DefinitionReference | None = None

    def __post_init__(self) -> None: ...

    # unit and ontology_term are mutually exclusive; both None remains valid for inline codes.
    # unit must resolve to UnitDefinition. Its binding is authoritative for external unit provenance.
    # Member labels/meanings describe this vocabulary entry; code remains the exact operational value.


@dataclass(frozen=True, kw_only=True)
class ValueSetDefinition:
    membership: ValueSetMembership
    members: Sequence[ValueSetMember]
    kind: Literal[DefinitionKind.VALUE_SET] = DefinitionKind.VALUE_SET

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Nonempty distinct string codes. OPEN permits unlisted codes; CLOSED forbids them.


@dataclass(frozen=True, kw_only=True)
class RelationshipDefinition:
    source_concept_id: DefinitionReference
    target_concept_id: DefinitionReference
    cardinality: RelationshipCardinality
    kind: Literal[DefinitionKind.RELATIONSHIP] = DefinitionKind.RELATIONSHIP


@dataclass(frozen=True, kw_only=True, init=False)
class Role:
    id: RoleId
    name: str
    display_name: str
    meaning: str
    evidence: tuple[Evidence, ...]

    def __init__(
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> None: ...


@dataclass(frozen=True, kw_only=True, init=False)
class Activity:
    id: ActivityId
    name: str
    display_name: str
    role_ids: tuple[RoleId, ...]
    input_ids: tuple[DefinitionReference, ...]
    output_ids: tuple[DefinitionReference, ...]
    decision_id: DefinitionReference | None
    evidence: tuple[Evidence, ...]

    def __init__(
        self,
        *,
        display_name: str | None = None,
        name: str | None = None,
        roles: Sequence[Role | RoleId] = (),
        inputs: Sequence[Definition | DefinitionReference] = (),
        outputs: Sequence[Definition | DefinitionReference] = (),
        decision: Definition[BusinessDecisionDefinition] | DefinitionReference | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> None: ...
    @property
    def referenced_definitions(self) -> tuple[Definition, ...]: ...
    @property
    def referenced_roles(self) -> tuple[Role, ...]: ...

    # Read-only authoring context: inspected snapshots supplied to the constructor, excluded from wire/hash.
    # Normalize public objects to typed stored IDs/pins; never fetch missing roles or model definitions.


@dataclass(frozen=True, kw_only=True, init=False)
class Event:
    id: EventId
    name: str
    display_name: str
    kind: EventKind
    evidence: tuple[Evidence, ...]

    def __init__(
        self,
        *,
        kind: EventKind,
        display_name: str | None = None,
        name: str | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> None: ...


@dataclass(frozen=True, kw_only=True, init=False)
class Gateway:
    id: GatewayId
    name: str
    display_name: str
    kind: GatewayKind
    direction: GatewayDirection

    def __init__(
        self,
        *,
        kind: GatewayKind,
        direction: GatewayDirection,
        display_name: str | None = None,
        name: str | None = None,
    ) -> None: ...


@dataclass(frozen=True, kw_only=True, init=False)
class Condition:
    id: ConditionId
    name: str
    display_name: str
    description: str
    input_ids: tuple[str, ...]
    expression: str  # Descriptive supported expression, never executable code.
    evidence: tuple[Evidence, ...]

    def __init__(
        self,
        *,
        description: str,
        expression: str,
        display_name: str | None = None,
        name: str | None = None,
        input_ids: Sequence[str] = (),
        evidence: Sequence[Evidence] = (),
    ) -> None: ...

    # Shared with business decisions; symbolic expression input keys retain their separate string contract.


type ProcessNodeId = ActivityId | EventId | GatewayId


@dataclass(frozen=True, kw_only=True, init=False)
class Flow:
    id: FlowId
    name: str
    display_name: str
    source_id: ProcessNodeId
    target_id: ProcessNodeId
    kind: FlowKind
    condition_id: ConditionId | None
    evidence: tuple[Evidence, ...]

    def __init__(
        self,
        *,
        source: Activity | Event | Gateway | ProcessNodeId,
        target: Activity | Event | Gateway | ProcessNodeId,
        display_name: str | None = None,
        name: str | None = None,
        kind: FlowKind = FlowKind.NORMAL,
        condition: Condition | ConditionId | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> None: ...
    @property
    def referenced_nodes(self) -> tuple[Activity | Event | Gateway, ...]: ...
    @property
    def referenced_conditions(self) -> tuple[Condition, ...]: ...

    # Runtime-only constructor snapshots, excluded from wire/hash; no implicit insertion into the process.


@dataclass(frozen=True, kw_only=True)
class ProcessDefinition:
    activities: Sequence[Activity]
    events: Sequence[Event]
    roles: Sequence[Role]
    flows: Sequence[Flow]
    gateways: Sequence[Gateway] = ()
    conditions: Sequence[Condition] = ()
    kind: Literal[DefinitionKind.PROCESS] = DefinitionKind.PROCESS

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.
    @property
    def referenced_definitions(self) -> tuple[Definition, ...]: ...

    # Aggregate activity authoring snapshots for the builder; conflicting revisions/scopes fail.
    # All six child constructors generate one nominal ID and resolve display_name/optional name.
    # No caller-supplied IDs at creation. Rebuilds retain supplied record IDs; codecs preserve stored IDs.
    # Names share one namespace across all child kinds; names and ID wire values must be unique per process.
    # Raise ProcessPartAlreadyExistsError; no suffix, implicit merge, name-derived ID or global name registry.
    # Every role, node and condition reference must resolve to the explicitly supplied child collections.
    # Supplied object snapshots must match those children exactly; foreign/conflicting snapshots fail.
    # Input/output model references and optional business decisions remain distinct from process-local IDs.
    # Constructors freeze inputs immediately. Runtime-only snapshots are absent after wire decoding.
    # Stored edges remain IDs/pins; plan bindings retain inspected model revisions for submission/review.
    # Shared Condition names are owner-local in business decisions too; their rules use ConditionId.
    # Validate structural start/end/flow/branch rules without executing expressions or creating work items.


@dataclass(frozen=True, kw_only=True)
class DecisionInput:
    id: str
    name: str
    definition_id: DefinitionReference
    data_type: DataType


@dataclass(frozen=True, kw_only=True)
class DecisionOutput:
    id: str
    name: str
    definition_id: DefinitionReference  # Meaning of the output, not a reference-valued result.
    data_type: ScalarDataType  # Initial table results are scalar literals only.


@dataclass(frozen=True, kw_only=True)
class DecisionRule:
    id: str
    condition_ids: Sequence[ConditionId]
    output_values: Sequence[tuple[str, DecisionValue]]  # Output id -> validated typed literal.
    evidence: Sequence[Evidence] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class BusinessDecisionDefinition:
    inputs: Sequence[DecisionInput]
    outputs: Sequence[DecisionOutput]
    conditions: Sequence[Condition]
    rules: Sequence[DecisionRule]
    hit_policy: HitPolicy = HitPolicy.UNIQUE
    kind: Literal[DefinitionKind.BUSINESS_DECISION] = DefinitionKind.BUSINESS_DECISION

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class RuleDefinition:
    statement: str
    constraints: Sequence[ConstraintDefinition] = ()
    kind: Literal[DefinitionKind.RULE] = DefinitionKind.RULE

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ModelTermReference:
    definition: DefinitionReference
    entity_kind: OntologyEntityKind
    local_path: Sequence[str] = ()  # E.g. ("attributes", attribute_id); never arbitrary RDF text.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Checked against the resolved body: concept -> class; relationship -> object property;
    # scalar/code attribute -> data property; reference/structured attribute -> object property.
    # Structured values -> class; value sets/checks have no direct OWL class role in this mapping.
    # UnitDefinition -> INDIVIDUAL (dk:Unit); a provenance term never makes it a SKOS concept.
    # Attribute paths use AttributeId.value on wire, not the display name.


@dataclass(frozen=True, kw_only=True)
class SemanticLinkDefinition:
    subject: ModelTermReference | OntologyTermReference
    relation: SemanticRelation
    object: ModelTermReference | OntologyTermReference
    kind: Literal[DefinitionKind.SEMANTIC_LINK] = DefinitionKind.SEMANTIC_LINK
    # Predicate-specific endpoint checks. SKOS links require SKOS concepts, not arbitrary classes.
    # Identity links never merge SDK IDs. External resources resolve through adopted modules/packs.


@dataclass(frozen=True, kw_only=True)
class OntologyModuleDefinition:
    ontology: OntologyClosure
    kind: Literal[DefinitionKind.ONTOLOGY_MODULE] = DefinitionKind.ONTOLOGY_MODULE
    # Reviewed adoption of a complete immutable standard module; source bytes retained intentionally.
    # Core checks closure/identity. Logical consistency requires a selected reasoning validator.


type DefinitionBody = (
    ConceptDefinition
    | RelationshipDefinition
    | ProcessDefinition
    | BusinessDecisionDefinition
    | RuleDefinition
    | SemanticLinkDefinition
    | OntologyModuleDefinition
    | ValueSetDefinition
    | UnitDefinition
    | StructuredValueDefinition
    | AcceptanceCheckDefinition
)


@dataclass(frozen=True, kw_only=True)
class ReferenceAlignment:
    reference_id: ReferenceDefinitionId
    reference_pack: ReferencePackPin
    relation: MappingRelation
    reason: str


@dataclass(frozen=True, kw_only=True)
class Definition[BodyT: DefinitionBody = DefinitionBody]:
    id: DefinitionId  # Stable company-local identity; never an upstream IRI reused with a new meaning.
    scope: ModelScope
    revision: int
    name: str  # Stable lookup name, unique across model-owned definition identities.
    display_name: str
    meaning: str
    body: BodyT
    aliases: Sequence[str] = ()
    terminology: Terminology = Terminology()
    evidence: Sequence[Evidence] = ()
    origin: DefinitionOrigin = DefinitionOrigin.COMPANY
    status: DefinitionStatus = DefinitionStatus.PROPOSED
    basis: EvidenceBasis = EvidenceBasis.HYPOTHESIS
    provenance: Sequence[ExtractionProvenance] = ()
    schema_origins: Sequence[SchemaOrigin] = ()
    alignments: Sequence[ReferenceAlignment] = ()
    decision_ids: Sequence[DecisionId] = ()
    rationale: str | None = None
    baseline_definition_id: DefinitionId | None = None  # In the model's exact direct baseline.
    replacement_ids: Sequence[DefinitionId] = ()  # Retirement lineage; never an automatic redirect.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Concept(Definition[ConceptDefinition]):
    # Same immutable definition record, with read conveniences; no additional state or wire kind.
    def __post_init__(self) -> None: ...  # Freeze base fields and require ConceptDefinition body.
    @property
    def attributes(self) -> tuple[AttributeDefinition, ...]: ...
    @property
    def keys(self) -> tuple[KeyDefinition, ...]: ...
    def get_attribute(
        self, *, name: str | None = None, attribute_id: AttributeId | None = None
    ) -> AttributeDefinition: ...
    def get_key(self, *, name: str | None = None, key_id: KeyId | None = None) -> KeyDefinition: ...

    # Exactly one selector. Exact owner-local lookup in this inspected revision, with no I/O.
    # Missing entries raise AttributeNotFoundError/KeyNotFoundError; never search labels/aliases.
    # Properties expose the body's frozen tuples; reading them creates no editable child builder.


@dataclass(frozen=True, kw_only=True)
class Process(Definition[ProcessDefinition]):
    # Same definition wire kind/state; child lookup is local to this inspected revision.
    def __post_init__(self) -> None: ...  # Freeze base fields; require ProcessDefinition body.
    @property
    def roles(self) -> tuple[Role, ...]: ...
    def get_role(self, *, name: str | None = None, role_id: RoleId | None = None) -> Role: ...
    @property
    def activities(self) -> tuple[Activity, ...]: ...
    def get_activity(
        self, *, name: str | None = None, activity_id: ActivityId | None = None
    ) -> Activity: ...
    @property
    def events(self) -> tuple[Event, ...]: ...
    def get_event(self, *, name: str | None = None, event_id: EventId | None = None) -> Event: ...
    @property
    def flows(self) -> tuple[Flow, ...]: ...
    def get_flow(self, *, name: str | None = None, flow_id: FlowId | None = None) -> Flow: ...
    @property
    def gateways(self) -> tuple[Gateway, ...]: ...
    def get_gateway(
        self, *, name: str | None = None, gateway_id: GatewayId | None = None
    ) -> Gateway: ...
    @property
    def conditions(self) -> tuple[Condition, ...]: ...
    def get_condition(
        self, *, name: str | None = None, condition_id: ConditionId | None = None
    ) -> Condition: ...

    # Exactly one selector; exact stable name or typed ID, never a label/alias or cross-process search.
    # Missing -> ProcessPartNotFoundError. Properties/getters perform no I/O and return frozen records.
    # Child changes are owning-definition revisions; no independent child persistence/review lifecycle.


@dataclass(frozen=True, kw_only=True)
class DefinitionChange:
    kind: DefinitionChangeKind
    # Describes a change; merge/separate are not unreviewed mutation commands.
    before: Sequence[Definition]
    after: Sequence[Definition]
    evidence: Sequence[Evidence] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class SourceAlignment:
    proposal_id: ProposalId
    definition_id: DefinitionId | None
    definition_revision: int | None
    disposition: SourceDisposition
    evidence: Sequence[Evidence]
    decision_id: DecisionId | None
    rationale: str
    context_fingerprint: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReferenceDisposition:
    definition_id: DefinitionId
    disposition: ReferenceDispositionKind
    decision_id: DecisionId | None
    rationale: str


@dataclass(frozen=True, kw_only=True)
class SourceAlignmentChange:
    before: SourceAlignment | None
    after: SourceAlignment | None


@dataclass(frozen=True, kw_only=True)
class ReferenceDispositionChange:
    before: ReferenceDisposition | None
    after: ReferenceDisposition | None


@dataclass(frozen=True, kw_only=True)
class DefinitionCorrespondence:
    before_id: DefinitionId
    after_id: DefinitionId
    # Same identity for revisions; explicit baseline lineage for a derived model.


@dataclass(frozen=True, kw_only=True)
class ChangeSet:
    scope: ModelScope  # Target/after scope, including for a baseline comparison.
    changes: Sequence[DefinitionChange]
    compatibility: Compatibility
    comparison: ComparisonKind
    before: SnapshotReference | None
    after: SnapshotReference | None
    before_reference_pack: ReferencePackPin | None
    after_reference_pack: ReferencePackPin | None
    before_dependencies: Sequence[ModelVersion]
    after_dependencies: Sequence[ModelVersion]
    correspondences: Sequence[DefinitionCorrespondence] = ()
    source_alignment_changes: Sequence[SourceAlignmentChange] = ()
    reference_disposition_changes: Sequence[ReferenceDispositionChange] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Snapshot diff requires before/after pins; initial has no before.
    # Live proposal previews have no snapshot pins; ReviewImpact pins workspace_revision.
    # No label-based matching. Normalize local references through explicit correspondences.
    # Compatibility concerns the declared contract, never consumer migration/execution safety.


@dataclass(frozen=True, kw_only=True)
class InterpretationContext:
    scope: ModelScope
    model_description: str
    workspace_revision: int
    reference_pack: ReferencePackPin | None
    approved_definitions: Sequence[Definition]
    baseline: ModelVersion | None
    dependencies: Sequence[ModelVersion]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Description participates in context fingerprints; never copy it into definitions.
```

```python
# src/domain_kernel/_shared/domain/proposals.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.enums import (
    EvidenceBasis,
)

from domain_kernel.review.domain.identifiers.proposal_id import ProposalId


from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from domain_kernel._shared.domain.contracts import Evidence, ExtractionProvenance, ModelScope
from domain_kernel._shared.domain.definitions import Definition


@dataclass(frozen=True, kw_only=True)
class Proposal:
    id: ProposalId
    scope: ModelScope
    definition: Definition
    basis: EvidenceBasis
    evidence: Sequence[Evidence]
    provenance: ExtractionProvenance
    confidence: Decimal | None = None  # Never approval or attributed confirmation.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


# Confidence is optional, finite and in [0, 1]; it never establishes approval.
```

```python
# src/domain_kernel/_shared/domain/review.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.model_values import Terminology

from domain_kernel._shared.domain.enums import (
    ConfirmationMethod,
    MappingRelation,
)

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)


from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self

from domain_kernel._shared.domain.contracts import (
    Evidence,
    Person,
    ReferencePackPin,
    SourceRevision,
)
from domain_kernel.modeling.domain.reference_packs import ReferenceDefinition
from domain_kernel._shared.domain.definitions import (
    Definition,
    DefinitionBody,
    ReferenceAlignment,
)

# Immutable model decisions; host applications own actor verification and routing.


@dataclass(frozen=True, kw_only=True)
class Accept:
    # Applies exact proposed addition/revision/retirement/restoration and mappings atomically.
    # Lifecycle changes check the inspected definition's expected revision.
    # For pack-change/change-set parents, approves the whole inspected plan, never a subset.
    # With no pack, approval creates no reference disposition; core/evidence checks still apply.
    reason: str
    kind: Literal["accept"] = "accept"


@dataclass(frozen=True, kw_only=True)
class EditDefinition:
    # Edits/approves proposed content in a compatible pending case, not an arbitrary approved ID.
    # Cannot change identity, retire a definition or bypass the revision-proposal path.
    definition_id: DefinitionId
    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    reason: str
    aliases: Sequence[str] = ()
    terminology: Terminology = Terminology()
    kind: Literal["edit_definition"] = "edit_definition"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Reserved lookup names cannot change; unresolved discovery names must be resolved before acceptance.


@dataclass(frozen=True, kw_only=True)
class Reject:
    # Cancel pending proposed effects with the current case version, even if target is obsolete.
    # Never apply target changes or waive underlying required model obligations.
    # Parent rejection also rejects its generated members; pre-existing included cases are released.
    reason: str
    kind: Literal["reject"] = "reject"


@dataclass(frozen=True, kw_only=True)
class MapToDefinition:
    definition: Definition
    reason: str
    kind: Literal["map_to_definition"] = "map_to_definition"

    @property
    def definition_id(self) -> DefinitionId: ...  # definition.id; no duplicated field.
    @property
    def definition_revision(self) -> int: ...  # definition.revision; no duplicated field.

    # Retain the immutable inspected snapshot, including scope, identity and revision.
    # Construction performs no I/O. Direct preview/submission reload and validate exact content,
    # active local status and scope; reject stale/modified/foreign targets, never substitute latest.
    # Generated planned mappings use validated prospective snapshots under the same atomic plan guards.
    # Decision codecs preserve the snapshot; derived properties are not serialized fields.


@dataclass(frozen=True, kw_only=True, init=False)
class MapToReference:
    local_definition: Definition
    reference_definition: ReferenceDefinition
    reference_pack: ReferencePackPin
    relation: MappingRelation
    reason: str
    kind: Literal["map_to_reference"] = "map_to_reference"

    def __init__(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        relation: MappingRelation,
        reason: str,
    ) -> None: ...
    @property
    def definition_id(self) -> DefinitionId: ...  # local_definition.id.
    @property
    def definition_revision(self) -> int: ...  # local_definition.revision.
    @property
    def reference_id(self) -> ReferenceDefinitionId: ...  # reference_definition.id.

    # Constructed by ReviewCase relationship factories; preserve both inspected snapshots.
    # Capture the reference's containing-pack pin; reject an unassociated reference snapshot.
    # Persist that pin explicitly with both snapshots; derived IDs/revision are not wire fields.
    # Codecs restore reference runtime context from this pin without embedding it recursively.
    # Preview/submission recheck local scope/revision/content and selected pack pin/reference content.
    # Reject foreign/stale/modified targets; never substitute latest or merge identities.
    # Existing map_to_reference discriminator and MappingRelation wire values remain unchanged.


@dataclass(frozen=True, kw_only=True)
class ApproveLocalExtension:
    definition_id: DefinitionId
    reason: str
    relationships: Sequence[ReferenceAlignment] = ()
    kind: Literal["local_extension"] = "local_extension"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Requires an explicit local identity, meaning and model ownership in the reviewed definition.


@dataclass(frozen=True, kw_only=True)
class Exclude:
    scope_text: str
    reason: str
    kind: Literal["exclude"] = "exclude"


@dataclass(frozen=True, kw_only=True)
class Defer:
    question: str
    reason: str
    kind: Literal["defer"] = "defer"  # Remains a blocker until resolved/reclassified legitimately.


@dataclass(frozen=True, kw_only=True)
class KeepNonblockingQuestion:
    scope_text: str
    reason: str
    kind: Literal["keep_nonblocking_question"] = "keep_nonblocking_question"
    # Reject for required reference_pack obligations or required evidence/confirmation gaps.


@dataclass(frozen=True, kw_only=True)
class Confirmation:
    confirmed_by: Person
    method: ConfirmationMethod
    confirmed_at: datetime
    evidence: Sequence[Evidence]
    recorded_by: str
    recorded_at: datetime
    authority: str  # Host-supplied attribution; SDK does not authenticate business authority.
    authenticated_actor: str | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Recorded confirmation is distinct from a host-verified authenticated action.
    # The host verifies identity/authority; the kernel checks scope, subject and required evidence.


@dataclass(frozen=True, kw_only=True)
class AnswerQuestion:
    answer: str
    reason: str
    confirmation: Confirmation | None = None
    kind: Literal["answer_question"] = "answer_question"


@dataclass(frozen=True, kw_only=True)
class ConfirmStatement:
    confirmation: Confirmation
    reason: str
    kind: Literal["confirm_statement"] = "confirm_statement"

    @classmethod
    def _from_statement(
        cls,
        *,
        revision: SourceRevision,
        evidence: Sequence[Evidence],
        authority: str,
        reason: str,
    ) -> Self: ...

    # Internal pure domain construction; the public SDK-boundary factory adapts IngestedSource.
    # No sources API dependency (including type-only), clock reads or I/O.
    # Require revision.origin to be StatementOrigin, known timezone-aware stated_at and nonempty evidence.
    # All citations and their processing.source must match revision exactly, including project/origin.
    # Copy speaker -> confirmed_by, stated_at -> confirmed_at, recorded_by/recorded_at unchanged,
    # and freeze-copy evidence. Set RECORDED and authenticated_actor=None, with no overrides.
    # Require non-blank authority/reason; never infer authority from role or confirmation from text.
    # InvalidDecisionError for wrong origin, absent time/evidence, inconsistent citations or invalid
    # attribution/timestamps. Unknown statement times remain valid for ordinary ingestion.
    # Never substitute ingestion/current time for confirmed_at or refresh the recorded_at timestamp.
    # Caller explicitly selects this capture; construction performs no review, audit or persistence.
    # Normal review rechecks compatible case/project, exact stored statement provenance and evidence
    # requirements; neither the factory nor caller-supplied authority authenticates the confirmer.
    # Same complete Confirmation payload and confirm_statement discriminator; no factory-only wire fields.
    # Direct construction remains available for explicit records, including authenticated confirmations.


type ContentChangeAction = (
    Accept | EditDefinition | MapToDefinition | MapToReference | ApproveLocalExtension | Exclude
)

type ReviewAction = (
    Accept
    | EditDefinition
    | Reject
    | MapToDefinition
    | MapToReference
    | ApproveLocalExtension
    | Exclude
    | Defer
    | KeepNonblockingQuestion
    | AnswerQuestion
    | ConfirmStatement
)
```

```python
# src/domain_kernel/_shared/domain/authoring.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.dependencies import DependencyChangeRequest

from domain_kernel._shared.domain.model_values import Terminology

from dataclasses import dataclass
from typing import Literal

from domain_kernel._shared.domain.contracts import Evidence, ModelScope, SchemaOrigin
from domain_kernel._shared.domain.definitions import Definition, DefinitionBody
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel._shared.domain.review import (
    ApproveLocalExtension,
    ContentChangeAction,
    Exclude,
    MapToDefinition,
    MapToReference,
)


@dataclass(frozen=True, kw_only=True)
class MapToPlannedDefinition:
    definition_id: DefinitionId
    reason: str
    kind: Literal["map_to_planned_definition"] = "map_to_planned_definition"
    # Must target a created/revised/restored identity in this plan; resolves to its final snapshot.
    # Submission emits ordinary MapToDefinition member actions; never valid as a direct review action.


type MappingCorrectionAction = (
    MapToDefinition | MapToReference | ApproveLocalExtension | Exclude | MapToPlannedDefinition
)


@dataclass(frozen=True, kw_only=True)
class AuthoredContent:
    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    aliases: Sequence[str] = ()
    terminology: Terminology = Terminology()
    evidence: Sequence[Evidence] = ()
    schema_origins: Sequence[SchemaOrigin] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class CreateDefinition:
    definition_id: DefinitionId  # Minted locally; reserved only at submission.
    content: AuthoredContent
    reason: str
    kind: Literal["create_definition"] = "create_definition"


@dataclass(frozen=True, kw_only=True)
class ReviseDefinition:
    before: Definition  # Exact inspected immutable snapshot, not just an ID.
    content: AuthoredContent  # Full replacement; builder preserves omitted edit fields.
    reason: str
    kind: Literal["revise_definition"] = "revise_definition"


@dataclass(frozen=True, kw_only=True)
class RetireDefinition:
    before: Definition
    replacement_ids: Sequence[DefinitionId]
    reason: str
    kind: Literal["retire_definition"] = "retire_definition"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class RestoreDefinition:
    before: Definition  # Must be retired; no simultaneous content edit of this identity.
    reason: str
    kind: Literal["restore_definition"] = "restore_definition"


@dataclass(frozen=True, kw_only=True)
class CorrectMapping:
    case_id: ReviewCaseId
    expected_version: int
    decision: MappingCorrectionAction
    proposal_ids: Sequence[ProposalId] | None
    reason: str
    kind: Literal["correct_mapping"] = "correct_mapping"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class IncludeCase:
    case_id: ReviewCaseId
    expected_version: int
    decision: (
        ContentChangeAction | MapToPlannedDefinition
    )  # Explicit action, never inferred from discovery.
    kind: Literal["include_case"] = "include_case"


type PlannedOperation = (
    CreateDefinition
    | ReviseDefinition
    | RetireDefinition
    | RestoreDefinition
    | CorrectMapping
    | IncludeCase
)


@dataclass(frozen=True, kw_only=True)
class ModelChangePlan:
    id: ChangePlanId
    scope: ModelScope
    expected_workspace_revision: int
    reason: str
    bindings: Sequence[Definition]  # Existing referenced definitions at inspected revisions.
    operations: Sequence[PlannedOperation]
    dependency_change: DependencyChangeRequest | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Detached immutable values; no builders, callbacks, provider objects or database handles.
    # Empty operations allowed only for a non-noop dependency_change; otherwise reject an empty plan.
    # No duplicate identities/targets, contradictory writes or foreign scope.
    # New/changed bare body references must be created/bound; unchanged inspected references retain guards.
    # Order is for display/audit; validation considers one prospective graph, not sequential mutation.
    # Every field participates in canonical request hashing; an ID never authorizes a mutation.
```

```python
# src/domain_kernel/authoring.py
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Final
from domain_kernel._shared.domain.authoring import (
    MapToPlannedDefinition,
    MappingCorrectionAction,
    ModelChangePlan,
)
from domain_kernel._shared.domain.contracts import (
    CompanyDefinitionReference,
    DefinitionReference,
    Evidence,
)
from domain_kernel._shared.domain.definitions import (
    AttributeDefinition,
    Concept,
    ConceptDefinition,
    ConstraintDefinition,
    RelationshipDefinition,
    UnitDefinition,
    ValueSetDefinition,
    Definition,
    DefinitionBody,
    ValueSetMember,
    Activity,
    Event,
    Flow,
    Role,
    Gateway,
    Condition,
    ProcessDefinition,
)
from domain_kernel._shared.domain.model_values import (
    CollectionKind,
    Count,
    Nullability,
    RelationshipCardinality,
    Terminology,
    ValueSetMembership,
)
from domain_kernel._shared.domain.ontology_assets import OntologyTermReference
from domain_kernel._shared.domain.data_shapes import AttributeType, KeyDefinition
from domain_kernel._shared.domain.dependencies import DependencyChangeRequest
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel._shared.domain.review import ContentChangeAction
from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.review.domain.models import ReviewCase


class Unset(Enum):
    VALUE = "unset"


UNSET: Final = Unset.VALUE
# Authoring-only omission marker; never stored or serialized in a plan or definition.


class DomainModelBuilder:
    def __init__(self, *, model_info: ModelInfo) -> None: ...
    # Capture the inspected model_info.revision; construction/building perform no I/O.
    # For new authoring on an existing model, reload via its owning Project.get_model first.
    # A fresh create_model result needs no extra reload. Never refresh/rebase a built plan implicitly.
    # Submission rechecks the workspace; further changes fail stale, while retries retain the same plan.
    def add_definition(
        self,
        *,
        meaning: str,
        body: DefinitionBody,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId: ...
    def add_concept(
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        attributes: Sequence[AttributeDefinition] = (),
        keys: Sequence[KeyDefinition] = (),
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId: ...
    def add_process(
        self,
        *,
        meaning: str,
        activities: Sequence[Activity],
        events: Sequence[Event],
        roles: Sequence[Role],
        flows: Sequence[Flow],
        display_name: str | None = None,
        name: str | None = None,
        gateways: Sequence[Gateway] = (),
        conditions: Sequence[Condition] = (),
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId: ...

    def add_unit(
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        symbol: str | None = None,
        ontology_term: OntologyTermReference | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> DefinitionId: ...
    def add_value_set(
        self,
        *,
        meaning: str,
        membership: ValueSetMembership,
        members: Sequence[ValueSetMember],
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        referenced_definitions: Sequence[Definition] = (),
    ) -> DefinitionId: ...
    def add_quantity(
        self,
        *,
        meaning: str,
        units: Definition[ValueSetDefinition] | DefinitionReference,
        quantity_kind: OntologyTermReference | None = None,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> DefinitionId: ...
    # add_unit creates one UnitDefinition under the shared naming/review contract.
    # Typed edit_unit/remove_unit/restore_unit use the same ordinary definition operations.
    # add_value_set creates the ordinary ValueSetDefinition; member.unit is a typed graph edge.
    # Planned units bind within this builder. Existing local unit IDs need inspected snapshots in
    # referenced_definitions on this call; qualified references retain exact dependency pins.
    # Traversal/remapping covers member.unit in review, packs, baselines, slices, codecs and imports.
    # add_quantity creates ONE StructuredValueDefinition: required=True, SINGLE, non-null DECIMAL magnitude
    # (unfaceted) and ValueSetType unit, both with None item bounds and QuantityBinding to these fields.
    # Fixed names magnitude/unit and display names Magnitude/Unit; generate IDs once and bind them.
    # Repeated builds retain those IDs. No new unit set is created.
    # units resolves to a CLOSED value set: inline codes, unit references and ontology-bound codes are valid.
    # Omitted quantity_kind remains None; QuantityBinding still exists. Preserve every supplied term pin.
    # No lookup, conversion, ontology adoption, field-ID inference or approval.
    def add_relationship(
        self,
        *,
        meaning: str,
        source: Definition[ConceptDefinition] | CompanyDefinitionReference,
        target: Definition[ConceptDefinition] | CompanyDefinitionReference,
        cardinality: RelationshipCardinality,
        display_name: str | None = None,
        name: str | None = None,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
    ) -> DefinitionId: ...
    def edit_definition(
        self,
        *,
        definition: Definition,
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        body: DefinitionBody | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Evidence] | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None: ...
    def edit_concept(
        self,
        *,
        concept: Concept,
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        attributes: Sequence[AttributeDefinition] | Unset = UNSET,
        keys: Sequence[KeyDefinition] | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Evidence] | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None: ...
    def add_attribute(
        self,
        *,
        concept: Concept,
        attribute: AttributeDefinition,
        referenced_definitions: Sequence[Definition] = (),
    ) -> AttributeId: ...
    def edit_attribute(
        self,
        *,
        concept: Concept,
        attribute: AttributeDefinition,
        display_name: str | Unset = UNSET,
        value_type: AttributeType | Unset = UNSET,
        required: bool | Unset = UNSET,
        collection: CollectionKind | Unset = UNSET,
        min_items: Count | None | Unset = UNSET,
        max_items: Count | None | Unset = UNSET,
        nullability: Nullability | Unset = UNSET,
        constraints: Sequence[ConstraintDefinition] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        referenced_definitions: Sequence[Definition] = (),
    ) -> None: ...
    def remove_attribute(self, *, concept: Concept, attribute: AttributeDefinition) -> None: ...
    def add_key(self, *, concept: Concept, key: KeyDefinition) -> KeyId: ...
    def edit_key(
        self,
        *,
        concept: Concept,
        key: KeyDefinition,
        display_name: str | Unset = UNSET,
        attributes: Sequence[AttributeId] | Unset = UNSET,
    ) -> None: ...
    def remove_key(self, *, concept: Concept, key: KeyDefinition) -> None: ...
    def edit_relationship(
        self,
        *,
        relationship: Definition[RelationshipDefinition],
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        source: Definition[ConceptDefinition] | CompanyDefinitionReference | Unset = UNSET,
        target: Definition[ConceptDefinition] | CompanyDefinitionReference | Unset = UNSET,
        cardinality: RelationshipCardinality | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Evidence] | Unset = UNSET,
    ) -> None: ...
    def remove_definition(
        self, *, definition: Definition, replacements: Sequence[Definition | DefinitionId] = ()
    ) -> None: ...
    def remove_concept(
        self,
        *,
        concept: Concept,
        replacements: Sequence[Definition[ConceptDefinition] | DefinitionId] = (),
    ) -> None: ...
    def remove_relationship(
        self,
        *,
        relationship: Definition[RelationshipDefinition],
        replacements: Sequence[Definition[RelationshipDefinition] | DefinitionId] = (),
    ) -> None: ...
    def restore_definition(self, *, definition: Definition) -> None: ...
    def restore_concept(self, *, concept: Concept) -> None: ...
    def restore_relationship(self, *, relationship: Definition[RelationshipDefinition]) -> None: ...
    def edit_unit(
        self,
        *,
        unit: Definition[UnitDefinition],
        display_name: str | Unset = UNSET,
        meaning: str | Unset = UNSET,
        symbol: str | None | Unset = UNSET,
        ontology_term: OntologyTermReference | None | Unset = UNSET,
        aliases: Sequence[str] | Unset = UNSET,
        terminology: Terminology | Unset = UNSET,
        evidence: Sequence[Evidence] | Unset = UNSET,
    ) -> None: ...
    def remove_unit(
        self,
        *,
        unit: Definition[UnitDefinition],
        replacements: Sequence[Definition[UnitDefinition] | DefinitionId] = (),
    ) -> None: ...
    def restore_unit(self, *, unit: Definition[UnitDefinition]) -> None: ...
    # Same identity/name, kind, scope, revision and prospective-state guards as generic operations.
    # UNSET preserves fields; explicit None clears symbol/ontology_term. No unit conversion.
    # Typed replacements must resolve to local units; no new plan/wire operation kinds.
    def change_dependencies(self, *, change: DependencyChangeRequest) -> None: ...
    def add_change_plan(self, *, plan: ModelChangePlan) -> None: ...
    def correct_mapping(
        self,
        *,
        case: ReviewCase,
        decision: MappingCorrectionAction,
        proposal_ids: Sequence[ProposalId] | None = None,
    ) -> None: ...
    def include_case(
        self, *, case: ReviewCase, decision: ContentChangeAction | MapToPlannedDefinition
    ) -> None: ...
    def build_change_plan(self, *, reason: str) -> ModelChangePlan: ...

    # add_process constructs the ordinary ProcessDefinition; no second builder, execution or new wire kind.
    # It and generic add_definition/edit_definition collect process.referenced_definitions into plan.bindings.
    # IDs without runtime snapshots require explicit referenced_definitions unless already represented/planned.
    # Stored bodies contain only IDs/pins. Revalidate all scopes/kinds/revisions at submission and acceptance.
    # Full process revisions use edit_definition(body=...); reused untouched child records retain IDs/names.
    # Child constructors create new identities; any replacement must explicitly repair dependent local edges.
    # Creation resolves display_name/name by the model-level definition naming contract.
    # SDK-generated DefinitionId values are provisional until submission; no name-derived identity.
    # Typed methods check body kind at runtime as well as exposing narrowed static types.
    # Existing objects register exact inspected snapshots; no public use/register step or hidden I/O.
    # Bare local IDs must already be planned or represented by an inspected snapshot in this plan.
    # Pinned references must match declared dependencies; submission checks materialized resources.
    # For IDs embedded in raw bodies/attributes, referenced_definitions supplies snapshots in the same call.
    # Normalize objects to stored IDs and plan.bindings; stored bodies never embed full definitions.
    # Conflicting snapshots, foreign objects and unknown local IDs fail; no implicit latest lookup.
    # An edited/restored endpoint resolves to the plan's final state, retaining its before-revision guard.
    # Omitted edit fields preserve inspected content; explicit empty sequences clear/replace collections.
    # None remains invalid for non-nullable edit fields; attribute item bounds explicitly accept None.
    # For SET/LIST, min_items=None resets to Count(value=0), max_items=None removes the upper bound.
    # Switching to SINGLE requires clearing any stored item counts explicitly; never silently drop them.
    # SINGLE -> SET/LIST normalizes inherited None bounds to zero/unbounded; required is preserved.
    # Validate the combined final attribute. UNSET preserves fields and never enters frozen content.
    # Preserve untouched schema origins/evidence; no identity/name/status/revision edit parameters.
    # No-effect edits emit no revision. Child edits accumulate into ONE parent ReviseDefinition.
    # Check every child against the same inspected concept; add_* returns the supplied child's ID.
    # Whole attributes/keys replacement conflicts with child operations on that collection.
    # Disjoint concept metadata edits may accompany child edits; repeated/conflicting child writes fail.
    # Parent removal/restoration conflicts with edits; restore then edit later.
    # Validate the final graph: explicitly repair/remove keys, quantity bindings and other dependents.
    # Removing children retains earlier parent revisions/bundles; never cascades or rewrites instance data.
    # Definition/concept/relationship/unit removal emits RetireDefinition; child removal revises its owner.
    # Preserve history; no hard delete, redirect or cascade.
    # Replacements must be active in the prospective local model and preserve acyclic lineage.
    # No discard API for unsubmitted additions; construct a fresh builder for revised draft intent.
    # Model description stays on model_info; definition qualifications belong in meaning.
    # Terminology None on additions resolves to empty metadata; never infer translations.
    # Copy and validate sequence inputs; str/bytes are not valid sequence containers here.
    # add_change_plan preserves included reasons/IDs; same scope/workspace revision required.
    # Existing review actions retain their reasons; only eligible content/alignment cases can be included.
    # No groups, pack changes, questions or confirmations; mapping corrections retain reopen rules.
    # Dependency-bearing plans allow revisions/removals plus remappings, no top-level additions/includes.
    # Child edits/additions/removals are owner revisions and must satisfy the same final-reference checks.
    # Validate edited refs against after pins; remap only otherwise untouched definitions.
    # build_change_plan requires a non-blank reason for the plan and newly authored operations.
    # Pure local draft; validate/freeze-copy; same content/reason returns the same plan ID.
    # Changed content/reason creates a new ID; prior plans remain immutable.
    # Empty/no-effect plans fail except valid dependency-only changes. No state changes before submission.


# Public facade for pure application helpers; no new domain slice or graph/database engine.
# Builders compose shared records. Repositories, inference and third-party imports are forbidden here.
```

```python
# src/domain_kernel/shared/identifiers/audit_id.py
from dataclasses import dataclass
from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class AuditId(OpaqueIdentifier):
    """Identity of an immutable durable-action audit record."""
```

```python
# src/domain_kernel/_shared/domain/audit.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel._shared.domain.contracts import Artifact


class AuditAction(StrEnum):
    CREATE_PROJECT = "create_project"
    CREATE_MODEL = "create_model"
    INGEST_SOURCE = "ingest_source"
    INGEST_SOURCE_REVISION = "ingest_source_revision"
    CAPTURE_SOURCE_MANIFEST = "capture_source_manifest"
    PROFILE_SOURCE = "profile_source"
    COPY_SOURCE_ORIGINAL = "copy_source_original"
    DISCOVER = "discover"
    EXTRACT_PROPOSALS = "extract_proposals"
    RESUME_DISCOVERY = "resume_discovery"
    PROPOSE_ALIGNMENT = "propose_alignment"
    PROPOSE_CHANGE = "propose_change"
    REOPEN_REVIEW_CASE = "reopen_review_case"
    DECIDE_REVIEW = "decide_review"
    COMPILE = "compile"
    VALIDATE = "validate"
    PREPARE_PUBLICATION = "prepare_publication"
    PUBLISH = "publish"
    EXPORT = "export"


class AuditOutcome(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class AuditResource:
    resource_id: (
        ProjectId
        | ModelId
        | DefinitionId
        | SourceId
        | SourceRevisionId
        | SourceManifestId
        | EvidenceId
        | DiscoveryRunId
        | DiscoveryDraftId
        | AlignmentId
        | ChangePlanId
        | ReviewCaseId
        | DecisionId
        | CandidateId
        | ValidationReportId
        | PublicationId
        | ApprovalId
        | BundleId
    )
    revision: int | None
    content_hash: ContentHash
    # Exact retained historical resource, never latest. Hash also pins unnumbered metadata/profile records.
    # Profile hashes include their source revision and profiling fingerprint; retain the referenced result.


@dataclass(frozen=True, kw_only=True)
class AuditRecord:
    id: AuditId
    project_id: ProjectId
    model_id: ModelId | None
    action: AuditAction
    outcome: AuditOutcome
    actor: str
    recorded_at: datetime
    before: Sequence[AuditResource | Artifact]
    after: Sequence[AuditResource | Artifact]
    reason: str | None = None
    parent_id: AuditId | None = None
    requested_artifact: Artifact | None = (
        None  # Copy/export intent; expected location/hash, not proof of a write.
    )

    def __post_init__(self) -> None: ...  # Validate attribution/scope and freeze sequence fields.

    # SDK-generated identity/time. Parent links preserve operation/group ancestry without duplicating effects.
    # STARTED/FAILED never claim successful intended effects; after may reference a persisted failed run.
    # Blocked preparation points to its stored diagnostic snapshot; publication success records its bundle.
    # requested_artifact retains write intent; SUCCEEDED verifies bytes and records the actual artifact in after.
    # Reuse typed decisions/plans/revisions for detailed effects; operational audit is not bundled wholesale.
```

```python
# src/domain_kernel/_shared/application/persistence.py
from __future__ import annotations

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.content_hash import ContentHash

from collections.abc import Callable
from domain_kernel._shared.domain.audit import AuditRecord
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel._shared.domain.contracts import Page
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class Invocation:
    project_id: ProjectId
    model_id: ModelId | None  # None only for project-scoped sources/catalog operations.
    operation: str  # Internal registered operation name; not caller-selectable.
    idempotency_key: str  # Resolved caller key, documented identity default or fresh internal key.
    request_hash: ContentHash  # Includes actor as well as canonical intent.
    actor: str
    parent_audit_id: AuditId | None = None


@dataclass(frozen=True, kw_only=True)
class Lease:
    token: str
    owner: str
    expires_at: datetime


@dataclass(frozen=True, kw_only=True)
class OperationOutcome:
    resource_kind: str  # Internal registered operation-result codec key, not a public choice.
    resource_id: str  # Persistence-boundary encoding; codec restores its nominal ID before lookup.
    resource_version: str | None = None


class IdempotencyRepository(Protocol):
    # Registered codecs validate resource kind/operation compatibility and reconstruct typed IDs.
    # Keys are unique within (project_id, model_id, operation, idempotency_key); actor is in request_hash.
    # Resolve optional public keys once before claim; internal retries/checkpoints reuse that invocation.
    # request_hash is never the default key; fresh unkeyed calls do not imply cross-call replay.
    # Nested/resumed work retains parent attribution; each durable commit includes its own audit outcome.
    # Same key/hash replays the outcome; a different hash raises IdempotencyConflictError.
    async def claim(self, *, invocation: Invocation, owner: str) -> Lease | OperationOutcome: ...
    async def complete(
        self, *, invocation: Invocation, lease: Lease, outcome: OperationOutcome
    ) -> None: ...
    async def renew(self, *, invocation: Invocation, lease: Lease) -> Lease: ...
    async def release(self, *, invocation: Invocation, lease: Lease) -> None: ...


class AuditRepository(Protocol):
    async def append(self, *, record: AuditRecord) -> None: ...
    async def list(
        self,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[AuditRecord]: ...

    # Append only, same transaction as state/outcome; no update/delete operation.
    # Model filter None means all project events; cursor binds scope/filter and a stable ordered snapshot.
    # Exact before/after resources remain retrievable; reject cross-scope/invalid parent references.
    # Retain external-write intent/expected hash and recover uncertain outcomes by verification.


class TransactionManager(Protocol):
    @abstractmethod
    def begin(self) -> AbstractAsyncContextManager[None]: ...

    # Require a clean session. Commit on normal exit; rollback on pre-commit failure.
    # Propagate cancellation/commit errors; an uncertain commit is not proof of rollback.
    # Never join an active transaction, create implicit savepoints or retry automatically.


class Transaction(TransactionManager, Protocol):
    # Composition-only repository bundle sharing one operation-local session.
    # Services receive narrow collaborators, including TransactionManager, individually.
    @property
    def audit(self) -> AuditRepository: ...
    @property
    def operations(self) -> IdempotencyRepository: ...


class UnitOfWorkFactory[T: Transaction](Protocol):
    # Resource scope only: acquire fresh bound adapters; service owns begin() and completion.
    # Close resources on every exit, with no second commit or abandoned cleanup.
    # No downloads, parsing, inference, or human waiting inside begin().
    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[T]: ...


type Clock = Callable[[], datetime]
type IdentifierFactory[IdT] = Callable[[], IdT]
```

```python
# src/domain_kernel/_shared/application/inference.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain_kernel._shared.domain.contracts import Evidence


@dataclass(frozen=True, kw_only=True)
class InferenceInput:
    text: str  # Untrusted source data, separate from SDK instructions.
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ModelRequest:
    instructions: str
    inputs: Sequence[InferenceInput]
    response_schema_json: str
    request_id: str
    timeout_seconds: float

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ModelResponse:
    output_json: str  # SDK validates this against its own response contract.
    model_id: str
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class ModelGateway(Protocol):
    # Caller owns provider/model/auth/transport and its lifecycle; no public fallback.
    # Runtime membership checks protocol presence only, not signatures or response validity.
    async def generate(self, *, request: ModelRequest) -> ModelResponse: ...
```

```python
# src/domain_kernel/_shared/application/storage.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.content_hash import ContentHash

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from domain_kernel._shared.domain.contracts import (
    Artifact,
    ConsumerObligation,
    SemanticArtifactMetadata,
)


@dataclass(frozen=True, kw_only=True)
class ArtifactWrite:
    project_id: ProjectId
    model_id: ModelId | None
    store: str
    key: str
    media_type: str
    expected_hash: ContentHash
    projection_limits: Sequence[str] = ()
    semantic: SemanticArtifactMetadata | None = None
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


class ArtifactStore(Protocol):
    # Names resolve only to configured destinations. Keys stay inside project scope.
    # Exact bytes/hash and stored metadata verified; immutable writes.
    # Reuse requires matching content and all projection/semantic/obligation metadata.
    # Metadata disagreement at an existing key raises ArtifactConflictError.
    # Preserve request metadata in the returned/stored Artifact; no stripping at the storage boundary.
    def put(self, *, request: ArtifactWrite, chunks: Iterable[bytes]) -> Artifact: ...
    def get(self, *, artifact: Artifact, max_bytes: int) -> bytes: ...
    def verify(self, *, artifact: Artifact) -> bool: ...
```

```python
# src/domain_kernel/configuration.py
from __future__ import annotations

from collections.abc import Sequence

from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, InstanceOf, StrictBool
from pydantic.json_schema import SkipJsonSchema

from domain_kernel._shared.application.inference import ModelGateway

type PositiveInt = Annotated[int, Field(strict=True, gt=0)]
type NonEmpty = Annotated[str, Field(min_length=1)]


class ConfigurationModel(BaseModel):
    # Validate and snapshot Sequence fields to tuples, including defaults; frozen=True is not sufficient.
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )


class Env(ConfigurationModel):
    env: NonEmpty

    def __init__(self, *, env: str) -> None: ...  # Supports Env(env="VARIABLE").


class SQLite(ConfigurationModel):
    type: Literal["sqlite"] = "sqlite"
    path: str | Path = ".domain-kernel/state.sqlite3"


class PostgreSQL(ConfigurationModel):
    type: Literal["postgresql"] = "postgresql"
    dsn: Env


type DatabaseConfiguration = Annotated[SQLite | PostgreSQL, Field(discriminator="type")]


class AwsProfile(ConfigurationModel):
    provider: Literal["aws_profile"] = "aws_profile"
    profile: NonEmpty


class AwsDefaultChain(ConfigurationModel):
    provider: Literal["aws_default_chain"] = "aws_default_chain"


class AwsStatic(ConfigurationModel):
    provider: Literal["aws_static"] = "aws_static"
    access_key_id: Env
    secret_access_key: Env
    session_token: Env | None = None


type AwsCredentials = Annotated[
    AwsProfile | AwsDefaultChain | AwsStatic,
    Field(discriminator="provider"),
]


class EntraClientSecret(ConfigurationModel):
    provider: Literal["entra_client_secret"] = "entra_client_secret"
    tenant_id: str | Env
    client_id: str | Env
    client_secret: Env


class FilesystemReader(ConfigurationModel):
    type: Literal["filesystem"] = "filesystem"
    name: NonEmpty
    root: str | Path


class S3Reader(ConfigurationModel):
    type: Literal["s3"] = "s3"
    name: NonEmpty
    bucket: NonEmpty
    prefix: str = ""
    region: str | None = None
    credentials: AwsCredentials


class SharePointReader(ConfigurationModel):
    type: Literal["sharepoint"] = "sharepoint"
    name: NonEmpty
    drive_id: NonEmpty
    root_item_id: NonEmpty
    credentials: EntraClientSecret


type ReaderConfiguration = Annotated[
    FilesystemReader | S3Reader | SharePointReader,
    Field(discriminator="type"),
]


class FilesystemStore(ConfigurationModel):
    type: Literal["filesystem"] = "filesystem"
    name: NonEmpty
    root: str | Path


class S3Store(ConfigurationModel):
    type: Literal["s3"] = "s3"
    name: NonEmpty
    bucket: NonEmpty
    prefix: str = ""
    region: str | None = None
    credentials: AwsCredentials


type StoreConfiguration = Annotated[FilesystemStore | S3Store, Field(discriminator="type")]


class OpenpyxlParser(ConfigurationModel):
    type: Literal["openpyxl"] = "openpyxl"


class DoclingParser(ConfigurationModel):
    type: Literal["docling"] = "docling"


class DuckDBParser(ConfigurationModel):
    type: Literal["duckdb"] = "duckdb"


class RdfLibParser(ConfigurationModel):
    type: Literal["rdflib"] = "rdflib"


class Parsers(ConfigurationModel):
    # None selects the format default on use; explicit adapters require their extra.
    excel: OpenpyxlParser | None = None
    documents: DoclingParser | None = None
    csv: DuckDBParser | None = None
    ontology: RdfLibParser | None = None


class Storage(ConfigurationModel):
    artifact_store: StoreConfiguration = Field(
        default_factory=lambda: FilesystemStore(name="artifacts", root=".domain-kernel/artifacts"),
    )
    additional_stores: Sequence[StoreConfiguration] = ()  # Extra approved CopyTo destinations.


class InMemoryProcessing(ConfigurationModel):
    mode: Literal["memory"] = "memory"
    max_source_bytes: PositiveInt = 64 * 1024 * 1024
    max_concurrent_sources: PositiveInt = 2
    max_expanded_bytes: PositiveInt = 256 * 1024 * 1024  # Proposed resource defaults.
    max_pages: PositiveInt = 1000


class Retention(ConfigurationModel):
    originals: StrictBool = False
    extracted_text: StrictBool = False
    evidence_excerpts: StrictBool = False


class SourceSelectionLimits(ConfigurationModel):
    max_files: PositiveInt = 1000
    max_listing_entries: PositiveInt = 10000
    max_listing_depth: PositiveInt = 32
    listing_timeout_seconds: PositiveInt = 60
    # Whole-call enumeration budgets, including filtered entries and traversal; no silent truncation.


class InferencePolicy(ConfigurationModel):
    timeout_seconds: Annotated[float, Field(gt=0)] = 60.0
    max_attempts: PositiveInt = 3


class PublicationPolicy(ConfigurationModel):
    allow_reviewed_nonblocking_questions: StrictBool = True
    # Never bypass required gaps, confirmations, or reference_pack obligations.


class ReferencePackCatalog(ConfigurationModel):
    reader: ReaderConfiguration  # Direct typed approved reader; no public fallback.


class ClientConfiguration(ConfigurationModel):
    schema_version: Literal[1] = 1
    base_dir: str | Path = Field(default_factory=Path.cwd)
    env_file: str | Path | None = None
    database: DatabaseConfiguration = Field(default_factory=SQLite)
    # Omission selects lazy default SQLite initialization; explicit database settings require operator setup.
    # Preserve original field presence through validation/default normalization, not equality with SQLite().
    readers: Sequence[ReaderConfiguration] = Field(
        default_factory=lambda: (FilesystemReader(name="inputs", root="."),),
    )
    reference_packs: ReferencePackCatalog | None = (
        None  # No catalog: list is empty; get fails explicitly.
    )
    parsers: Parsers = Field(default_factory=Parsers)
    storage: Storage = Field(default_factory=Storage)
    processing: InMemoryProcessing = Field(default_factory=InMemoryProcessing)
    source_selection: SourceSelectionLimits = Field(default_factory=SourceSelectionLimits)
    retention: Retention = Field(default_factory=Retention)
    inference: InferencePolicy = Field(default_factory=InferencePolicy)
    model_gateway: SkipJsonSchema[InstanceOf[ModelGateway] | None] = Field(
        default=None,
        repr=False,
        exclude=True,
    )
    publication: PublicationPolicy = Field(default_factory=PublicationPolicy)

    # Validate unique names and compatible policies; Client snapshots settings but retains the gateway reference.
    # Runtime-only Python instance: reject classes/factories, strings and mappings; never instantiate/call it here.
    # InstanceOf checks protocol presence; static typing and invocation/response validation retain their roles.
    # Exclude the gateway from dumps, both JSON Schema modes, repr and sanitized diagnostics.
    # TOML/JSON input rejects the model_gateway key (even null); no Env, import path or automatic provider lookup.
    # JSON input guards enforce that rule before field validation; schema omission alone is not validation.
    # No broad arbitrary_types_allowed or SkipValidation; ordinary config fields stay strictly validated.
    # The host retains ownership; never deep-copy, close or serialize the gateway or its credentials.
    @classmethod
    def from_toml(
        cls,
        *,
        path: str | Path = "domain-kernel.toml",
        model_gateway: ModelGateway | None = None,
    ) -> ClientConfiguration: ...

    # Explicit file I/O via the shared private TOML parser; normalize named bindings and validate settings.
    # Always require the selected file, even with the default path; no fallback to defaults.
    # Missing, unreadable, non-file or invalid input -> ConfigurationError.
    # Reject runtime keys from the file before attaching the Python gateway argument; no overrides registry.
    # Resolve relative file paths from captured cwd, then base_dir from the file directory.
    # Retain Env/env_file references for Client resolution.
    # Preserve private source-path/origin and database-field-presence metadata through Client loading.
    # These are runtime provenance, not serialized configuration fields or caller-selectable overrides.
    # No secret resolution, adapter initialization or inference here; malformed input -> ConfigurationError.
    # reference_packs.reader must equal a registered reader, including its configuration, not only name.


type ConfigurationInput = str | Path | ClientConfiguration
```

```python
# src/domain_kernel/diagnostics.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path


@unique
class ConfigurationSource(StrEnum):
    DEFAULTS = "defaults"
    PYTHON = "python"
    TOML = "toml"


@unique
class DatabaseInitialization(StrEnum):
    AUTOMATIC = "automatic"
    EXPLICIT = "explicit"
    HOST_MANAGED = "host_managed"


@dataclass(frozen=True, kw_only=True)
class ConfigurationSetting:
    path: Sequence[str]
    value: str  # Allowlisted, redacted display summary; never a raw configuration round trip.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ConfigurationReport:
    source: ConfigurationSource
    source_path: Path | None
    base_dir: Path
    database_initialization: DatabaseInitialization
    settings: Sequence[ConfigurationSetting]
    integrations: Sequence[str]  # Registered names only; never provider objects or their repr.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Captured effective settings, origin and setup policy; not a connection/installation health report.
    # Allowlist safe summaries; omit secrets, credential/DSN values, secret references and provider repr.
    # Inspection/rendering performs no file, database, network or optional-adapter I/O.
```

```python
# src/domain_kernel/_settings.py
from __future__ import annotations

from collections.abc import Sequence

from pathlib import Path
from typing import ClassVar

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain_kernel._shared.application.inference import ModelGateway
from domain_kernel.diagnostics import ConfigurationSource

from domain_kernel.configuration import (
    ClientConfiguration,
    ConfigurationInput,
    ConfigurationModel,
    Env,
)


class ResolvedSecret(ConfigurationModel):
    reference: Env
    value: SecretStr = Field(repr=False, exclude=True)


class RuntimeSettings(BaseSettings):
    # Private: custom sources only; no default broad env overrides or global dotenv mutation.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )
    configuration: ClientConfiguration  # Snapshot settings; preserve model_gateway object identity.
    base_dir: Path
    configuration_source: ConfigurationSource
    configuration_path: Path | None
    database_explicit: bool
    secrets: Sequence[ResolvedSecret] = Field(default=(), repr=False, exclude=True)


# pydantic-settings is a required future dependency, not yet declared in pyproject.toml.
class PydanticConfigurationLoader:
    # TOML named credentials/stores/reference_pack reader -> typed objects; Python composes directly.
    # Resolve only explicit Env: process env > chosen .env > sanitized ConfigurationError.
    # Missing chosen .env fails; no automatic .env loading, parent search/interpolation or adapter/network creation.
    # Convert TOML arrays to tuples and string paths explicitly; preserve strict field types.
    def parse_toml(
        self, *, path: str | Path, model_gateway: ModelGateway | None = None
    ) -> ClientConfiguration: ...
    # Shared with ClientConfiguration.from_toml; path-only Client input uses model_gateway=None.
    # Strict file loading: missing, unreadable, non-file or invalid input -> ConfigurationError.
    # Capture cwd for relative file paths; settings paths then use the selected file's directory.
    # Reject serialized runtime keys first, then attach the supplied Python reference; preserve file-relative base.
    # Parse/validate only; Env resolution remains in load. Never import/construct a gateway from file data.
    def load(self, *, config: ConfigurationInput | None) -> RuntimeSettings: ...

    # None: check only captured cwd/domain-kernel.toml; genuine absence -> fresh ClientConfiguration defaults.
    # An existing but invalid, unreadable or non-file path raises ConfigurationError, never falls back.
    # No Git-root, parent-directory or global discovery; no merging files into supplied typed configuration.
    # File input calls parse_toml; typed input revalidates settings and keeps its exact gateway instance.
    # Snapshot once; later file/cwd changes cannot reload settings or rebase paths.
    # Preserve TOML origin and original database-field presence even through from_toml -> typed input.
    # Python inputs record explicit fields before default normalization; default equality is insufficient.
    # Do not snapshot via model_dump (drops gateway) or deep model_copy (copies caller-owned resources).
    # Never mutate caller config. Runtime settings retain no callable in serialized/persisted policy payloads.
```

For common validation, duplicate-name, missing-name, missing-capability and stale-state
failures, messages identify the operation/input and a practical next step while
preserving typed codes and structured issues. Optional spelling suggestions are
bounded to authorized names of the requested kind in the current scope; no inference,
full-catalog scan, cross-scope disclosure or automatic correction. If a suggestion
cannot be produced cheaply, return the original error unchanged. No universal repair
framework or exhaustive edge-case diagnostics are required.

Common exception bases and validation stay in `shared/errors.py`. Each typed
domain error lives in a separate module under its domain's `errors/` directory,
for example `review/domain/errors/invalid_decision_error.py`.

```python
# Proposed error inventory; concrete domain errors each have their own module.
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.contracts import Issue

if TYPE_CHECKING:
    # Type-only dependencies in the respective domain error modules, not the shared error base.
    from domain_kernel.modeling.domain.models import Publication
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment


class DomainKernelError(Exception):
    code: str
    retryable: bool

    def __init__(self, *, message: str, code: str, retryable: bool = False) -> None: ...


class ConfigurationError(DomainKernelError):
    issues: tuple[Issue, ...]  # Sanitized; raw Pydantic input/context/cause never escapes.

    def __init__(self, *, issues: Sequence[Issue]) -> None: ...


class ProjectNotFoundError(DomainKernelError): ...


class ProjectAlreadyExistsError(DomainKernelError): ...


class SourceNotFoundError(DomainKernelError): ...


class SourceAlreadyExistsError(DomainKernelError): ...


class SourceUnavailableError(DomainKernelError): ...


class EvidenceUnavailableError(DomainKernelError): ...


class SourceRevisionMismatchError(DomainKernelError): ...


class ResourceLimitError(DomainKernelError): ...


class UnsupportedCapabilityError(DomainKernelError): ...


class ProjectionBlockedError(UnsupportedCapabilityError):
    assessment: ProjectionAssessment

    def __init__(self, *, assessment: ProjectionAssessment) -> None: ...

    # Require assessment.exportable == False; preserve the exact immutable report.
    # Non-exportable assessment from Model.export/render; no artifact has been written.
    # Preserve availability, findings, obligations, issues, remedies and exact input/mapping pins.
    # Invalid input/scope and authentication/storage errors retain their own typed errors.
    # Diagnostic report only; no persisted publication-preparation snapshot is created.


class InvalidOntologyError(DomainKernelError):
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None: ...


class MissingDependencyError(DomainKernelError): ...


class AuthenticationError(DomainKernelError): ...


class InvalidDecisionError(DomainKernelError): ...


class StaleStateError(DomainKernelError): ...


class IdempotencyConflictError(DomainKernelError): ...


class OperationInProgressError(DomainKernelError): ...


class InferenceError(DomainKernelError): ...


class PublicationBlockedError(DomainKernelError):
    publication: Publication  # Exact immutable blocked snapshot, already committed and retrievable.

    def __init__(self, *, publication: Publication) -> None: ...
    @property
    def issues(self) -> tuple[Issue, ...]: ...  # Alias of publication.blockers; no separate copy.

    # prepare_publication raises only after persistence commits; never rolls back this snapshot.
    # Publishing a stored blocked publication raises this error too; stale state uses StaleStateError.


class VersionExistsError(DomainKernelError): ...


class ArtifactConflictError(DomainKernelError): ...


class AttributeNotFoundError(DomainKernelError): ...


class KeyNotFoundError(DomainKernelError): ...


class ProcessPartNotFoundError(DomainKernelError): ...


class ProcessPartAlreadyExistsError(DomainKernelError): ...


class AttributeAlreadyExistsError(DomainKernelError): ...


class KeyAlreadyExistsError(DomainKernelError): ...


class DefinitionNotFoundError(DomainKernelError): ...


class DefinitionAlreadyExistsError(DomainKernelError): ...


class DefinitionKindMismatchError(DomainKernelError): ...


class ModelNotFoundError(DomainKernelError): ...


class ModelAlreadyExistsError(DomainKernelError): ...


class ReferencePackNotFoundError(DomainKernelError): ...


class PatternNotFoundError(DomainKernelError): ...


class InvalidReferencePackError(DomainKernelError): ...


class UnsupportedReferencePackVersionError(DomainKernelError): ...


class ScopeMismatchError(DomainKernelError): ...


class PublicationNotFoundError(DomainKernelError): ...


class MissingCapabilityError(DomainKernelError): ...


class UnsupportedBundleVersionError(DomainKernelError): ...


class InvalidBundleError(DomainKernelError):
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None: ...


class InvalidChangePlanError(DomainKernelError):
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None: ...


class InvalidSchemaError(DomainKernelError):
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None: ...
```

```python
# src/domain_kernel/sources/domain/models.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.enums import (
    InferredColumnType,
)

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.sources.domain.identifiers.source_id import SourceId


from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from domain_kernel._shared.domain.contracts import (
    Artifact,
    Evidence,
    EvidenceLocator,
    Issue,
    Origin,
    ProcessingRecord,
    SourceRevision,
    StatementOrigin,
    ParsedSourceOrigin,
)
from domain_kernel._shared.domain.ontology import OntologyStatement


@dataclass(frozen=True, kw_only=True)
class Source:
    id: SourceId
    project_id: ProjectId
    name: str
    display_name: str
    version: int

    def __post_init__(self) -> None: ...  # Validate resolved names; never regenerate identity.

    def register_revision(self, *, revision: SourceRevision) -> Source: ...


@dataclass(frozen=True, kw_only=True)
class EvidenceContent:
    evidence: Evidence  # The resolved citation; distinct from the explicitly loaded content.
    excerpt: str  # Supporting text returned by an explicit get_evidence call.
    origin: Origin  # Actual verified acquisition used to load this content.


@dataclass(frozen=True, kw_only=True)
class ColumnProfile:
    name: str
    inferred_type: InferredColumnType
    nullable: bool
    identifier_candidate: bool
    provider_type_name: str | None = None  # Preserve an unknown provider-specific spelling.


@dataclass(frozen=True, kw_only=True)
class TableProfile:
    name: str
    columns: Sequence[ColumnProfile]
    row_count: int

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class SourceProfile:
    source: SourceRevision
    processing: ProcessingRecord
    tables: Sequence[TableProfile] = ()
    page_count: int | None = None
    sections: Sequence[str] = ()
    issues: Sequence[Issue] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


type CellValue = None | bool | int | float | str | date | datetime | Decimal


@dataclass(frozen=True, kw_only=True)
class TableBatch:
    table: str
    columns: Sequence[str]
    rows: Sequence[Sequence[CellValue]]
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class TextSection:
    text: str
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class OntologyFragment:
    statements: Sequence[OntologyStatement]
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


type ParsedChunk = TableBatch | TextSection | OntologyFragment


@dataclass(frozen=True, kw_only=True)
class OriginalCopy:
    source: SourceRevision
    artifact: Artifact
    verified_hash: ContentHash
    copied_at: datetime


@dataclass(frozen=True, kw_only=True)
class StatementPayload:
    text: str
    origin: StatementOrigin
    # Canonical digest includes text, speaker/role, stated_at, context, form, intent and schema.
    # Resolve recorded_by before hashing; it participates, while acquisition/recorded_at does not.
    # Unknown stated_at is canonical null; omitted/None input is equivalent, never clock-filled.


@dataclass(frozen=True, kw_only=True)
class StatementSnapshot:
    revision: SourceRevision
    payload: StatementPayload  # Explicitly captured content; immutable; edits create revisions.


@dataclass(frozen=True, kw_only=True)
class ParsedText:
    text: str
    locator: EvidenceLocator
    kind: Literal["text"] = "text"


@dataclass(frozen=True, kw_only=True)
class ParsedTable:
    name: str
    columns: Sequence[str]
    rows: Sequence[Sequence[CellValue]]
    locator: EvidenceLocator
    row_locators: Sequence[EvidenceLocator] = ()
    kind: Literal["table"] = "table"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ParsedGraph:
    statements: Sequence[OntologyStatement]
    locator: EvidenceLocator
    kind: Literal["graph"] = "graph"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


type ParsedPart = ParsedText | ParsedTable | ParsedGraph


@dataclass(frozen=True, kw_only=True)
class ParsedPayload:
    origin: ParsedSourceOrigin
    parts: Sequence[ParsedPart]
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Canonical hashing tags each scalar's exact type; date/decimal are not conflated with strings.
    # Excludes captured_at; includes upstream identity/revision/claimed digest and all content/locators.


@dataclass(frozen=True, kw_only=True)
class ParsedSnapshot:
    revision: SourceRevision
    processing: ProcessingRecord
    evidence: Sequence[Evidence]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Payload retention is controlled by extracted_text policy, not by the host capture operation.
```

```python
# src/domain_kernel/sources/application/contracts.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.shared.enums.issue_severity import IssueSeverity

from domain_kernel._shared.domain.enums import (
    OntologyFormat,
    StatementForm,
    StatementIntent,
)

from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId


from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from domain_kernel._shared.domain.contracts import (
    Evidence,
    Issue,
    Person,
    SourceRevision,
    ParsedSourceOrigin,
)
from domain_kernel.configuration import ConfigurationModel, NonEmpty, PositiveInt
from domain_kernel.sources.domain.models import ParsedPart, OriginalCopy
from pydantic import Field, model_validator


class ReaderLocation(ConfigurationModel):
    reader: NonEmpty
    path: NonEmpty  # Reader-relative; reject escapes from configured root/prefix.


class FileInput(ConfigurationModel):
    path: str | Path | None = None  # Shorthand for reader="inputs".
    location: ReaderLocation | None = None

    @model_validator(mode="after")
    def require_one_location(self) -> Self: ...  # Exactly one of path/location.


class Excel(FileInput):
    format: Literal["excel"] = "excel"
    sheets: Sequence[str] | None = None
    header_row: PositiveInt = 1


class CSV(FileInput):
    format: Literal["csv"] = "csv"
    delimiter: Annotated[str, Field(min_length=1, max_length=1)] = ","
    encoding: NonEmpty = "utf-8"
    header_row: PositiveInt = 1


class PDF(FileInput):
    format: Literal["pdf"] = "pdf"
    pages: Sequence[PositiveInt] | None = None  # One-based; full raw bytes still hashed.


class Word(FileInput):
    format: Literal["word"] = "word"


class Ontology(FileInput):
    format: Literal[
        OntologyFormat.TURTLE, OntologyFormat.RDFXML, OntologyFormat.JSONLD, OntologyFormat.NTRIPLES
    ] = OntologyFormat.TURTLE


type FileDescriptor = Annotated[
    Excel | CSV | PDF | Word | Ontology,
    Field(discriminator="format"),
]


class CopyTo(ConfigurationModel):
    store: NonEmpty  # Serializable destination name; validate against configured stores.


@dataclass(frozen=True, kw_only=True)
class IngestedSource:
    revision: SourceRevision
    processing_fingerprint: str
    retained_original: OriginalCopy | None = None
    evidence: Sequence[Evidence] = ()  # May be empty; citations do not embed excerpts.

    @property
    def source_id(self) -> SourceId: ...
    @property
    def revision_id(self) -> SourceRevisionId: ...

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


class Statement(ConfigurationModel):
    format: Literal["statement"] = "statement"
    text: NonEmpty
    speaker: Person
    recorded_by: NonEmpty | None = None
    stated_at: datetime | None = None
    context: NonEmpty
    form: StatementForm
    intent: StatementIntent

    # recorded_by omitted/None means the ingestion actor is recording this statement.
    # Resolve it once at ingestion; pure descriptor construction has no actor or clock dependency.
    # stated_at omitted/None means unknown; when supplied it must be timezone-aware.
    # context is required and never inherited from a model; form/intent have no implicit defaults.


# Recorded_at assigned by SDK clock; explicit capture persists this payload, not file bytes.
type SourceDescriptor = Annotated[
    Excel | CSV | PDF | Word | Ontology | Statement | ParsedSource,
    Field(discriminator="format"),
]


class ParsedSource(ConfigurationModel):
    format: Literal["normalized"] = (
        "normalized"  # Preserve the serialized tag and canonical format.
    )
    origin: ParsedSourceOrigin
    parts: Sequence[ParsedPart]
    # Validate nonempty parts, unique locators, rectangular tables and all resource limits.
    # Supplied content is untrusted input; upstream original hashes remain host assertions.


class IngestionStage(StrEnum):
    LISTING = "listing"
    NAMING = "naming"
    INGESTION = "ingestion"


class SourceEntryKind(StrEnum):
    FILE = "file"
    FOLDER = "folder"
    LINK = "link"


@dataclass(frozen=True, kw_only=True)
class SourceEntry:
    # Internal reader listing metadata; provider tokens never substitute for a content digest.
    location: ReaderLocation
    kind: SourceEntryKind
    provider_scope: str
    provider_item_id: str | None = None
    provider_version: str | None = None


class SourceInput(ConfigurationModel):
    source: SourceDescriptor
    display_name: str | None = None
    name: str | None = None
    retain_original: CopyTo | None = None
    idempotency_key: str | None = None
    # Same naming/validation as ingest_source; pure construction, no source creation.


class SourceFolder(ConfigurationModel):
    location: ReaderLocation
    recursive: bool = False
    include: Sequence[NonEmpty] = ()
    exclude: Sequence[NonEmpty] = ()
    name_prefix: str | None = None
    retain_original: CopyTo | None = None
    idempotency_key: str | None = None
    # A selection, not a Source. Validate prefix as a slug; strict bool and frozen sequences.
    # Empty include selects all files. Relative case-sensitive POSIX globs: * and ? stay
    # in one segment, ** as a whole segment spans zero or more levels; exclusions win.
    # Reject absolute/traversal patterns. recursive=False never descends, even with **.


@dataclass(frozen=True, kw_only=True)
class IngestionSuccess:
    input: SourceInput
    ingested_source: IngestedSource


@dataclass(frozen=True, kw_only=True)
class IngestionFailure:
    input: SourceInput | SourceFolder
    stage: IngestionStage
    issue: Issue
    retryable: bool
    location: ReaderLocation | None = None  # File/folder path; None for non-file inputs.

    # Read-only views of the same issue; no duplicated fields in construction or serialization.
    @property
    def message(self) -> str: ...  # issue.message, with the same sanitization.
    @property
    def code(self) -> str: ...  # issue.code.
    @property
    def severity(self) -> IssueSeverity: ...  # issue.severity; preserve the enum type.


@dataclass(frozen=True, kw_only=True)
class BatchIngestionResult:
    items: Sequence[IngestionSuccess | IngestionFailure]

    @property
    def successes(self) -> tuple[IngestionSuccess, ...]: ...
    @property
    def failures(self) -> tuple[IngestionFailure, ...]: ...
    @property
    def revisions(self) -> tuple[SourceRevision, ...]: ...  # Successful items only.

    def __post_init__(self) -> None: ...  # Validate and freeze; all views derive from items.

    # Caller selection order, then case-sensitive relative-path order within each folder.
    # One outcome per distinct selected file/non-file input, plus incomplete-listing failures.
    # Deduplicated entries retain their first position; completion timing never changes ordering.
    # An empty selection yields empty items/views. Successes remain after per-input failures;
    # callers inspect failures before deciding whether to continue with partial revisions.


@dataclass(frozen=True, kw_only=True)
class SourceManifestEntry:
    file: SourceEntry
    input: SourceInput  # Resolved names, descriptor/options and generated per-file request key.


@dataclass(frozen=True, kw_only=True)
class SourceManifest:
    # Internal application record; persisted selection metadata, not an original-file copy.
    id: SourceManifestId
    project_id: ProjectId
    provider_scope: str  # Resolved reader binding, retained even for an empty folder.
    selection: SourceFolder
    actor: str
    request_hash: ContentHash
    created_at: datetime
    items: Sequence[SourceManifestEntry | IngestionFailure]
    content_hash: ContentHash

    def __post_init__(self) -> None: ...  # Freeze and validate scope, paths, keys and hash.

    # Require FILE entries with matching file descriptors/locations and selection-bound failures.
    # Only a complete listing becomes an immutable manifest; unsupported formats/names remain
    # per-file failures in it. Hash all metadata except content_hash using the canonical codec.
    # Child keys are bound to manifest identity + canonical entry identity, never list positions.
    # Capture manifest + attributed audit + folder-key outcome atomically before content ingestion.
    # Retries load the same manifest; changed actor/selection/binding under its key conflicts.
    # Request hashing includes resolved provider scope, never credentials or gateway objects.
    # With no caller key, generate an internal invocation key and capture a new manifest; no cross-call replay.
```

```python
# src/domain_kernel/sources/application/service.py
from __future__ import annotations

from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId

from collections.abc import Sequence
from typing import Protocol

from domain_kernel._shared.domain.contracts import Evidence, Page, SourceRevision
from domain_kernel.sources.application.contracts import (
    BatchIngestionResult,
    CopyTo,
    IngestedSource,
    SourceDescriptor,
    SourceFolder,
    SourceInput,
)
from domain_kernel.sources.domain.models import EvidenceContent, OriginalCopy, Source, SourceProfile


class SourceRevisions(Protocol):
    async def get(
        self, *, source_id: SourceId, revision_id: SourceRevisionId
    ) -> SourceRevision: ...
    async def list(
        self,
        *,
        source_id: SourceId,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[SourceRevision]: ...


class EvidenceAccess(Protocol):
    # Reload the stored citation, enforce access/retention policy, verify source bytes.
    async def get(self, *, evidence: Evidence) -> EvidenceContent: ...


class Sources(Protocol):
    # ingest creates a named Source and initial revision; never upserts by name/path/digest.
    # Resolve display_name/name by the shared naming rules; at least one is required.
    # Project-local name collisions raise SourceAlreadyExistsError, including races.
    # ingest_revision requires an existing project-local ID; preserve its names and identity.
    # get requires exactly one selector (ValueError otherwise); exact local name/ID lookup.
    # Missing sources raise SourceNotFoundError; foreign IDs raise ScopeMismatchError.
    # Resolve stored project/source identity and digest before trusting revision metadata.
    # Replay matching idempotency outcomes before collision checks or source acquisition;
    # changed actor, target, naming inputs or descriptor under the same key conflicts.
    # Commit source/revision/evidence metadata, attributed audit and outcome atomically.
    # File/retention I/O stays outside transactions under the external-write recovery rules.
    # Statement captures in ingest/ingest_many/ingest_revision resolve omitted/None recorded_by
    # from that operation's actor before capture hashing; preserve explicit recorder and unknown stated_at.
    # Matching retries return the original capture and recorded_at, without reassigning attribution or times.
    @property
    def revisions(self) -> SourceRevisions: ...
    @property
    def evidence(self) -> EvidenceAccess: ...
    async def ingest(
        self,
        *,
        actor: str,
        source: SourceDescriptor,
        display_name: str | None = None,
        name: str | None = None,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource: ...
    async def ingest_many(
        self,
        *,
        actor: str,
        sources: Sequence[SourceInput | SourceFolder],
        max_concurrent_sources: int | None = None,
        max_files: int | None = None,
    ) -> BatchIngestionResult: ...
    async def ingest_revision(
        self,
        *,
        actor: str,
        source_id: SourceId,
        source: SourceDescriptor,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource: ...
    async def get(
        self, *, name: str | None = None, source_id: SourceId | None = None
    ) -> Source: ...
    async def list(self, *, limit: int = 50, cursor: PageCursor | None = None) -> Page[Source]: ...
    async def profile(self, *, actor: str, revision: SourceRevision) -> SourceProfile: ...
    # Only file origins have an original; statement/supplied origins reject original copying.
    async def copy_original(
        self,
        *,
        actor: str,
        revision: SourceRevision,
        destination: CopyTo,
        idempotency_key: str | None = None,
    ) -> OriginalCopy: ...
```

```python
# src/domain_kernel/sources/application/ports.py
from __future__ import annotations

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId

from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.domain.contracts import (
    Artifact,
    Evidence,
    FileOrigin,
    Page,
    ProcessingLimits,
    SourceRevision,
    ParsedSourceOrigin,
)
from domain_kernel.configuration import SourceSelectionLimits
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.application.contracts import (
    FileDescriptor,
    ReaderLocation,
    SourceEntry,
    SourceManifest,
)
from domain_kernel.sources.domain.models import (
    EvidenceContent,
    ParsedChunk,
    ParsedPayload,
    ParsedSnapshot,
    OriginalCopy,
    Source,
    SourceProfile,
    StatementPayload,
    StatementSnapshot,
)


class SeekableBytes(Protocol):
    def read(self, *, size: int = -1) -> bytes: ...
    def seek(self, *, offset: int, whence: int = 0) -> int: ...
    def tell(self) -> int: ...


@dataclass(frozen=True, kw_only=True)
class AcquiredSource:
    stream: SeekableBytes
    origin: FileOrigin
    byte_length: int
    content_hash: (
        ContentHash  # Hash all original bytes during acquisition, before format selection.
    )


class SourceReader(Protocol):
    # Bounded memory, seekable buffer; manager releases streams/buffers on every exit.
    def open(
        self,
        *,
        location: ReaderLocation,
        limits: ProcessingLimits,
        expected: SourceRevision | None = None,
        expected_entry: SourceEntry | None = None,
    ) -> AbstractAsyncContextManager[AcquiredSource]: ...
    # Enforce expected entry's provider scope/item/version when present; verify full bytes.
    # If both guards are supplied they must agree; unavailable pins fail, never use latest silently.
    async def list_children(
        self,
        *,
        location: ReaderLocation,
        limits: SourceSelectionLimits,
        limit: int = 100,
        cursor: PageCursor | None = None,
    ) -> Page[SourceEntry]: ...

    # Immediate children only; coordinator owns recursion, filtering and aggregate budgets.
    # Query-bound cursors; validate provider pagination targets against the configured binding.
    # Filesystem directories, SharePoint children and slash-delimited S3 prefixes share this contract.
    # Do not follow symlinks/shortcuts; report unsupported links and enforce root/prefix containment.
    # LINK entries become per-entry unsupported-capability failures, never traversed descendants.
    # Readers lacking listing raise MissingCapabilityError; built-in document readers support it.


class FormatParser(Protocol):
    # Run blocking parsers in a bounded worker; reject temp-file/disk-spill requirements.
    def parse(
        self,
        *,
        content: AcquiredSource,
        descriptor: FileDescriptor,
        limits: ProcessingLimits,
    ) -> Iterator[ParsedChunk]: ...


class NativeOriginalCopier(Protocol):
    # None means unsupported; otherwise copy the pinned provider version and verify its hash.
    def copy(
        self,
        *,
        source: SourceRevision,
        project_id: ProjectId,
        store: str,
        key: str,
    ) -> Artifact | None: ...


@dataclass(frozen=True, kw_only=True)
class SourceRevisionReference:
    # Internal persistence identity; public methods accept SourceRevision.
    project_id: ProjectId
    source_id: SourceId
    revision_id: SourceRevisionId

    @classmethod
    def from_revision(cls, *, revision: SourceRevision) -> SourceRevisionReference: ...


class SourceRepository(Protocol):
    async def get(self, *, project_id: ProjectId, source_id: SourceId) -> Source: ...
    async def find_by_name(self, *, project_id: ProjectId, name: str) -> Source | None: ...
    # Atomic unique (project_id, name); create never suffixes, retrieves or appends on collision.
    # save uses optimistic version checks; concurrent appends cannot overwrite source state.
    # add_revision is immutable and unique (project_id, source_id, revision_id).
    # Same bytes/payload under the same source reuse the revision; processing stays separate.
    # Preserve the original revision record; new acquisitions never overwrite its provenance.
    async def save(self, *, source: Source, expected_version: int | None) -> None: ...
    async def list(
        self, *, project_id: ProjectId, limit: int, cursor: PageCursor | None
    ) -> Page[Source]: ...
    async def get_revision(self, *, reference: SourceRevisionReference) -> SourceRevision: ...
    async def add_revision(self, *, revision: SourceRevision) -> None: ...
    async def list_revisions(
        self,
        *,
        project_id: ProjectId,
        source_id: SourceId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[SourceRevision]: ...
    async def save_profile(self, *, profile: SourceProfile) -> None: ...
    async def get_profile(
        self, *, reference: SourceRevisionReference, fingerprint: str
    ) -> SourceProfile | None: ...
    async def get_evidence(self, *, project_id: ProjectId, evidence_id: EvidenceId) -> Evidence: ...
    async def save_evidence(self, *, evidence: Evidence) -> None: ...
    # Content persists only when the explicit derivative-retention policy permits it.
    async def get_evidence_content(
        self, *, project_id: ProjectId, evidence_id: EvidenceId
    ) -> EvidenceContent | None: ...
    async def save_evidence_content(self, *, content: EvidenceContent) -> None: ...
    async def record_copy(self, *, copy: OriginalCopy) -> None: ...
    async def add_statement(self, *, snapshot: StatementSnapshot) -> None: ...
    async def add_parsed_snapshot(self, *, snapshot: ParsedSnapshot) -> None: ...
    async def get_parsed_snapshot(
        self, *, reference: SourceRevisionReference
    ) -> ParsedSnapshot: ...
    async def save_parsed_payload(
        self, *, reference: SourceRevisionReference, payload: ParsedPayload
    ) -> None: ...
    async def get_parsed_payload(
        self, *, reference: SourceRevisionReference
    ) -> ParsedPayload | None: ...
    async def get_statement(self, *, reference: SourceRevisionReference) -> StatementSnapshot: ...
    async def add_manifest(self, *, manifest: SourceManifest) -> None: ...
    async def get_manifest(
        self, *, project_id: ProjectId, manifest_id: SourceManifestId
    ) -> SourceManifest: ...
    async def find_manifest_for_item(
        self, *, project_id: ProjectId, idempotency_key: str
    ) -> SourceManifest | None: ...

    # Unique child-key ownership; immutable manifest + audit + folder idempotency result commit together.
    # Single/batch retries of generated child inputs reload their manifest and enforce actor,
    # request hash and stored entry guards; copying the input never drops its acquisition pin.


class SourcesTransaction(Transaction, Protocol):
    @property
    def sources(self) -> SourceRepository: ...


class StatementCanonicalizer(Protocol):
    def canonical_bytes(self, *, payload: StatementPayload) -> bytes: ...

    # Explicit schema version; excludes recorded_at/acquisition timestamps, includes resolved recorded_by/context.
    # Unknown stated_at serializes as null, distinct from any supplied timezone-aware timestamp.
    # Same canonical bytes -> same digest; not represented as an original file/provider version.


class ParsedSourceResolver(Protocol):
    # Host owns access control, transport, lifecycle and reconstruction of the captured payload.
    def open(
        self, *, origin: ParsedSourceOrigin, limits: ProcessingLimits
    ) -> AbstractAsyncContextManager[ParsedPayload]: ...

    # SDK recomputes the parsed capture digest and rejects a changed payload before exposing evidence.


class ParsedCanonicalizer(Protocol):
    def canonical_bytes(self, *, payload: ParsedPayload) -> bytes: ...
```

```python
# src/domain_kernel/sources/api/sources.py
from __future__ import annotations

from domain_kernel.sources.application.contracts import (
    CSV,
    PDF,
    CopyTo,
    Excel,
    FileDescriptor,
    IngestedSource,
    ParsedSource,
    Ontology,
    ReaderLocation,
    SourceDescriptor,
    SourceInput,
    SourceFolder,
    IngestionStage,
    IngestionSuccess,
    IngestionFailure,
    BatchIngestionResult,
    Statement,
    Word,
)
from domain_kernel.sources.application.ports import ParsedSourceResolver
from domain_kernel.sources.application.service import EvidenceAccess, SourceRevisions, Sources
from domain_kernel.sources.domain.models import (
    EvidenceContent,
    ParsedChunk,
    ParsedGraph,
    ParsedPart,
    ParsedPayload,
    ParsedSnapshot,
    ParsedTable,
    ParsedText,
    OriginalCopy,
    Source,
    SourceProfile,
    StatementPayload,
    StatementSnapshot,
)

__all__ = [
    "CSV",
    "PDF",
    "CopyTo",
    "Excel",
    "FileDescriptor",
    "IngestedSource",
    "ParsedSource",
    "Ontology",
    "ReaderLocation",
    "SourceDescriptor",
    "SourceInput",
    "SourceFolder",
    "IngestionStage",
    "IngestionSuccess",
    "IngestionFailure",
    "BatchIngestionResult",
    "Statement",
    "Word",
    "EvidenceAccess",
    "SourceRevisions",
    "Sources",
    "ParsedSourceResolver",
    "EvidenceContent",
    "ParsedChunk",
    "ParsedGraph",
    "ParsedPart",
    "ParsedPayload",
    "ParsedSnapshot",
    "ParsedTable",
    "ParsedText",
    "OriginalCopy",
    "Source",
    "SourceProfile",
    "StatementPayload",
    "StatementSnapshot",
]
```

```python
# src/domain_kernel/sources/infrastructure/readers.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain_kernel.configuration import FilesystemReader, S3Reader, SharePointReader
from domain_kernel.sources.application.ports import SourceReader
from pydantic import SecretStr


@dataclass(frozen=True, kw_only=True)
class AwsCredentialSnapshot:
    access_key_id: SecretStr
    secret_access_key: SecretStr
    session_token: SecretStr | None = None
    expires_at: datetime | None = None


class AwsCredentialProvider(Protocol):
    # Refresh through the selected native provider; never persist this credential snapshot.
    def get_credentials(self) -> AwsCredentialSnapshot: ...


class EntraTokenProvider(Protocol):
    def get_token(self, *, scope: str) -> SecretStr: ...


class FilesystemReaderAdapter(SourceReader):
    def __init__(self, *, config: FilesystemReader) -> None: ...


class S3ReaderAdapter(SourceReader):
    def __init__(self, *, config: S3Reader, credentials: AwsCredentialProvider) -> None: ...


class SharePointReaderAdapter(SourceReader):
    def __init__(self, *, config: SharePointReader, credentials: EntraTokenProvider) -> None: ...


# Optional vendor SDK imports occur only in their adapters; paths/tenant scope are enforced.
```

```python
# src/domain_kernel/sources/infrastructure/parsers.py
from __future__ import annotations

from domain_kernel.configuration import DoclingParser, DuckDBParser, OpenpyxlParser, RdfLibParser
from domain_kernel.sources.application.ports import FormatParser


class OpenpyxlParserAdapter(FormatParser):
    def __init__(self, *, config: OpenpyxlParser) -> None: ...


class DoclingParserAdapter(FormatParser):
    def __init__(self, *, config: DoclingParser) -> None: ...


class DuckDBParserAdapter(FormatParser):
    def __init__(self, *, config: DuckDBParser) -> None: ...


class RdfLibParserAdapter(FormatParser):
    def __init__(self, *, config: RdfLibParser) -> None: ...


# Every adapter must prove the memory/retention policy; no silent file-based workaround.
# Disable implicit network acquisition, including RDF contexts/imports; use approved readers.
```

```python
# src/domain_kernel/sources/infrastructure/stores.py
from __future__ import annotations

from domain_kernel._shared.application.storage import ArtifactStore
from domain_kernel.configuration import FilesystemStore, S3Store
from domain_kernel.sources.infrastructure.readers import AwsCredentialProvider


class FilesystemStoreAdapter(ArtifactStore):
    def __init__(self, *, config: FilesystemStore) -> None: ...


class S3StoreAdapter(ArtifactStore):
    def __init__(self, *, config: S3Store, credentials: AwsCredentialProvider) -> None: ...


# Optional native copying implements NativeOriginalCopier with the same pinned-hash guarantee.
```

Discovery instruction controls are keyword-only on `Model.discover()` and
`Model.extract_proposals()` (and the internal `Discovery.extract()` stage):

| Inputs | Effective discovery instructions |
|---|---|
| Neither supplied | Versioned SDK default |
| `additional_instructions` only | SDK default followed by the additional instructions |
| `prompt_override` supplied | Override only; default and additional instructions are ignored |

Supplied strings must be non-blank; invalid arguments fail before work begins.
`None` means omitted. These controls customize instructions, not the output contract:
`ModelRequest.response_schema_json` remains SDK-owned in every mode. Source evidence,
interpretation context and required response validation remain separate from the
customizable instructions. Existing bounded retries, typed errors, per-source failures
and recovery semantics are unchanged; invalid output never becomes a valid proposal.
There is no silent fallback from an override to the default prompt.

Capture `DiscoveryPrompt` before inference and expose the same immutable capture on
`DiscoveryDraft.prompt` and `DiscoveryResult.prompt`. The processing fingerprint pins
the effective instructions, exact response schema and interpretation context. Idempotency
request identity includes both supplied instruction values, even when an override makes
one ineffective; changed intent under the same key conflicts. Retries and
`resume_discovery()` reuse the capture instead of the current default or new instructions.
Changing instructions starts a new run. Neither prompt control selects source pages,
alters parsing, guarantees exhaustive/reproducible extraction, nor approves proposals.

```python
# src/domain_kernel/discovery/domain/models.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.shared.enums.issue_severity import IssueSeverity

from domain_kernel._shared.domain.enums import (
    RunStatus,
)

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId


from dataclasses import dataclass
from typing import Literal

from domain_kernel._shared.domain.contracts import (
    Issue,
    ModelScope,
    SourceRevision,
)
from domain_kernel._shared.domain.definitions import InterpretationContext


@dataclass(frozen=True, kw_only=True)
class DiscoveryPrompt:
    additional_instructions: str | None
    prompt_override: str | None
    default_prompt_version: str | None  # None when override replaces the default entirely.
    effective_instructions: str
    response_schema_version: str

    # SDK-created immutable capture, not a caller-supplied output schema or configuration object.
    # Validate supplied strings as non-blank; preserve exact text. Override wins over both other inputs.
    # Without override: versioned default + separately delimited additional instructions, if supplied.
    # Source material/model context remain separate inputs; neither is concatenated as trusted policy.
    # Persist before inference. Fingerprint effective prompt, response schema and interpretation context.


@dataclass(frozen=True, kw_only=True)
class DiscoveryDraft:
    id: DiscoveryDraftId
    scope: ModelScope
    run_id: DiscoveryRunId
    context: InterpretationContext
    source_revisions: Sequence[SourceRevision]
    proposals: Sequence[Proposal]
    prompt: DiscoveryPrompt
    processing_fingerprint: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class DiscoveryFailure:
    source_label: str
    source: SourceRevision | None
    issue: Issue
    retryable: bool

    # Read-only diagnostic views; preserve the underlying Issue and serialized fields.
    @property
    def message(self) -> str: ...  # issue.message, with the same sanitization.
    @property
    def code(self) -> str: ...  # issue.code.
    @property
    def severity(self) -> IssueSeverity: ...  # issue.severity; preserve the enum type.


@dataclass(frozen=True, kw_only=True)
class DiscoveryResult:
    id: DiscoveryRunId
    scope: ModelScope
    version: int
    status: RunStatus
    failures: Sequence[DiscoveryFailure]
    discovery_id: DiscoveryDraftId | None
    reconciliation_id: AlignmentId | None
    context: InterpretationContext
    prompt: DiscoveryPrompt

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class DiscoveryProgress:
    scope: ModelScope
    run_id: DiscoveryRunId
    stage: RunStatus
    completed: int
    total: int | None


@dataclass(frozen=True, kw_only=True)
class DiscoveryRun:
    snapshot: DiscoveryResult
    checkpoint: str | None

    def transition(self, *, status: RunStatus, expected_version: int) -> DiscoveryRun: ...
    def record_failure(self, *, failure: DiscoveryFailure) -> DiscoveryRun: ...
    def save_checkpoint(self, *, checkpoint: str) -> DiscoveryRun: ...


from domain_kernel._shared.domain.proposals import Proposal as Proposal
```

```python
# src/domain_kernel/discovery/application/service.py
from __future__ import annotations

from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.shared.identifiers.page_cursor import PageCursor

from collections.abc import Sequence
from typing import Protocol

from domain_kernel._shared.domain.contracts import Page, SourceRevision
from domain_kernel.discovery.domain.models import DiscoveryDraft, DiscoveryProgress, DiscoveryResult


class ProgressCallback(Protocol):
    def __call__(self, *, progress: DiscoveryProgress) -> None: ...


class Discovery(Protocol):
    # Bound to one model; never imports definitions from another model implicitly.
    async def get(self, *, run_id: DiscoveryRunId) -> DiscoveryResult: ...
    async def list(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[DiscoveryResult]: ...
    async def extract(
        self,
        *,
        actor: str,
        source_revisions: Sequence[SourceRevision],
        additional_instructions: str | None = None,
        prompt_override: str | None = None,
        idempotency_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DiscoveryDraft: ...
    async def resume(
        self,
        *,
        actor: str,
        run_id: DiscoveryRunId,
        idempotency_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DiscoveryResult: ...
```

```python
# src/domain_kernel/discovery/application/ports.py
from __future__ import annotations

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.shared.identifiers.page_cursor import PageCursor

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from domain_kernel._shared.application.persistence import Lease, Transaction
from domain_kernel._shared.domain.contracts import ModelScope, Page, SourceRevision
from domain_kernel._shared.domain.definitions import InterpretationContext
from domain_kernel.discovery.domain.models import (
    DiscoveryDraft,
    DiscoveryPrompt,
    DiscoveryResult,
    DiscoveryRun,
    Proposal,
)
from domain_kernel.sources.api.sources import ParsedChunk, SourceProfile


@dataclass(frozen=True, kw_only=True)
class SourceMaterial:
    profile: SourceProfile
    chunks: AsyncIterator[ParsedChunk]


class SourceCatalog(Protocol):
    def open(self, *, revision: SourceRevision) -> AbstractAsyncContextManager[SourceMaterial]: ...


class InterpretationContextReader(Protocol):
    async def get(self, *, scope: ModelScope) -> InterpretationContext: ...


class ProposalExtractor(Protocol):
    async def extract(
        self, *, material: SourceMaterial, context: InterpretationContext, prompt: DiscoveryPrompt
    ) -> tuple[Proposal, ...]: ...


class DiscoveryRepository(Protocol):
    async def get(self, *, scope: ModelScope, run_id: DiscoveryRunId) -> DiscoveryRun: ...
    async def add(self, *, run: DiscoveryRun) -> None: ...
    async def save(self, *, run: DiscoveryRun, expected_version: int, lease: Lease) -> None: ...
    async def list(
        self, *, scope: ModelScope, limit: int, cursor: PageCursor | None
    ) -> Page[DiscoveryResult]: ...
    async def save_draft(self, *, draft: DiscoveryDraft) -> None: ...
    async def get_draft(
        self, *, scope: ModelScope, discovery_id: DiscoveryDraftId
    ) -> DiscoveryDraft: ...


class DiscoveryTransaction(Transaction, Protocol):
    @property
    def discovery(self) -> DiscoveryRepository: ...
```

```python
# src/domain_kernel/discovery/application/extractor.py
from __future__ import annotations

from domain_kernel._shared.application.inference import ModelGateway
from domain_kernel.configuration import InferencePolicy
from domain_kernel.discovery.application.ports import ProposalExtractor


class StructuredProposalExtractor(ProposalExtractor):
    def __init__(self, *, gateway: ModelGateway, policy: InferencePolicy) -> None: ...

    # Use captured prompt.effective_instructions; do not append default/additional text to an override.
    # SDK still owns request schemas, evidence binding and response validation in every mode.
    # Preserve existing bounded retries, typed failures and checkpoint/recovery behavior.
    # Prompt customization never changes response_schema_json or admits invalid output.
```

```python
# src/domain_kernel/discovery/api/discovery.py
from __future__ import annotations

from domain_kernel._shared.domain.enums import (
    RunStatus,
)

from domain_kernel.discovery.application.service import Discovery, ProgressCallback
from domain_kernel.discovery.domain.models import (
    DiscoveryDraft,
    DiscoveryFailure,
    DiscoveryProgress,
    DiscoveryPrompt,
    DiscoveryResult,
    Proposal,
)

__all__ = [
    "Discovery",
    "ProgressCallback",
    "DiscoveryDraft",
    "DiscoveryFailure",
    "DiscoveryProgress",
    "DiscoveryPrompt",
    "DiscoveryResult",
    "Proposal",
    "RunStatus",
]
```

```python
# src/domain_kernel/reconciliation/domain/models.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.enums import (
    AlignmentLayer,
    AlignmentStatus,
    MappingRelation,
)

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.reconciliation.domain.identifiers.alignment_suggestion_id import (
    AlignmentSuggestionId,
)
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId


from dataclasses import dataclass
from typing import Literal

from domain_kernel._shared.domain.contracts import (
    Evidence,
    ModelScope,
    ReferencePackPin,
)


@dataclass(frozen=True, kw_only=True)
class AlignmentSuggestion:
    id: AlignmentSuggestionId
    scope: ModelScope
    layer: AlignmentLayer
    proposal_ids: Sequence[ProposalId]  # Group compatible occurrences to reduce review volume.
    definition_id: DefinitionId
    definition_revision: int
    reference_id: ReferenceDefinitionId | None
    relation: MappingRelation | None
    evidence: Sequence[Evidence]
    reason: str
    context_fingerprint: str  # Reuse only approved mappings with compatible meaning/context.
    reused_decision_id: DecisionId | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Alignment:
    id: AlignmentId
    scope: ModelScope
    discovery_id: DiscoveryDraftId
    reference_pack: ReferencePackPin | None
    version: int
    status: AlignmentStatus
    suggestions: Sequence[AlignmentSuggestion]

    def mark_prepared(self, *, expected_version: int) -> Alignment: ...

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.
```

```python
# src/domain_kernel/reconciliation/application/service.py
from __future__ import annotations

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId

from typing import Protocol

from domain_kernel.reconciliation.domain.models import Alignment


class Reconciliation(Protocol):
    async def propose(
        self,
        *,
        actor: str,
        discovery_id: DiscoveryDraftId,
        idempotency_key: str | None = None,
    ) -> Alignment: ...
    async def get(self, *, alignment_id: AlignmentId) -> Alignment: ...
```

```python
# src/domain_kernel/reconciliation/application/ports.py
from __future__ import annotations

from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId

from typing import Protocol

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.domain.contracts import ModelScope, ReferencePackPin
from domain_kernel._shared.domain.definitions import InterpretationContext
from domain_kernel.discovery.api.discovery import DiscoveryDraft
from domain_kernel.modeling.api.modeling import ReferencePack
from domain_kernel.reconciliation.domain.models import Alignment, AlignmentSuggestion


class DiscoveryDraftReader(Protocol):
    async def get_draft(
        self, *, scope: ModelScope, discovery_id: DiscoveryDraftId
    ) -> DiscoveryDraft: ...


class SimilarityScorer(Protocol):
    def score(self, *, left: str, right: str) -> float: ...


class ConceptMatcher(Protocol):
    # Same label + different meaning -> review; similarity is never equivalence.
    async def match(
        self, *, draft: DiscoveryDraft, context: InterpretationContext
    ) -> tuple[AlignmentSuggestion, ...]: ...


class ReviewPreparation(Protocol):
    # Cases + alignment checkpoint + idempotency result commit atomically.
    async def prepare(self, *, actor: str, alignment: Alignment) -> None: ...


class ReconciliationRepository(Protocol):
    async def get(self, *, scope: ModelScope, alignment_id: AlignmentId) -> Alignment: ...
    async def add(self, *, alignment: Alignment) -> None: ...
    async def save(self, *, alignment: Alignment, expected_version: int) -> None: ...


class ReconciliationTransaction(Transaction, Protocol):
    @property
    def reconciliation(self) -> ReconciliationRepository: ...


class ReferencePackSnapshotReader(Protocol):
    async def get(self, *, pin: ReferencePackPin) -> ReferencePack: ...
```

```python
# src/domain_kernel/reconciliation/application/matcher.py
from __future__ import annotations

from domain_kernel._shared.application.inference import ModelGateway
from domain_kernel.configuration import InferencePolicy
from domain_kernel.reconciliation.application.ports import (
    ConceptMatcher,
    ReferencePackSnapshotReader,
    SimilarityScorer,
)


class EvidenceBasedConceptMatcher(ConceptMatcher):
    def __init__(
        self,
        *,
        policy: InferencePolicy,
        reference_packs: ReferencePackSnapshotReader,
        similarity: SimilarityScorer | None = None,
        gateway: ModelGateway | None = None,
    ) -> None: ...

    # Deterministic identifiers/mappings/context matching works without inference.
    # Identifiers/approved mappings/context first; similarity never proves equivalence.
```

```python
# src/domain_kernel/reconciliation/api/reconciliation.py
from __future__ import annotations

from domain_kernel.reconciliation.application.service import Reconciliation
from domain_kernel.reconciliation.domain.models import Alignment, AlignmentSuggestion

__all__ = ["Reconciliation", "Alignment", "AlignmentSuggestion"]
```

```python
# src/domain_kernel/reconciliation/infrastructure/similarity.py
from __future__ import annotations

from domain_kernel.reconciliation.application.ports import SimilarityScorer


class RapidFuzzSimilarityScorer(SimilarityScorer):
    def __init__(self) -> None: ...  # Optional matching extra; score never commits a mapping.
```

```python
# src/domain_kernel/review/domain/decisions.py
from __future__ import annotations

from domain_kernel._shared.domain.review import (
    Accept,
    AnswerQuestion,
    ApproveLocalExtension,
    Confirmation,
    ConfirmStatement,
    ContentChangeAction,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    MapToDefinition,
    MapToReference,
    Reject,
    ReviewAction,
)

__all__ = [
    "Accept",
    "EditDefinition",
    "Reject",
    "MapToDefinition",
    "MapToReference",
    "ApproveLocalExtension",
    "Exclude",
    "Defer",
    "KeepNonblockingQuestion",
    "Confirmation",
    "AnswerQuestion",
    "ConfirmStatement",
    "ContentChangeAction",
    "ReviewAction",
]
```

```python
# src/domain_kernel/review/domain/models.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.domain.models import DependencyChange

from domain_kernel._shared.domain.authoring import ModelChangePlan

from domain_kernel._shared.domain.enums import (
    CaseKind,
    CaseStatus,
    Compatibility,
    QuestionDisposition,
    RequirementKind,
)

from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.content_hash import ContentHash


from dataclasses import dataclass
from datetime import datetime
from typing import Literal, overload

from domain_kernel._shared.domain.contracts import Evidence, Issue, ModelScope, ReferencePackPin
from domain_kernel._shared.domain.definitions import (
    ChangeSet,
    Definition,
    DefinitionChange,
    SourceAlignmentChange,
    ReferenceDispositionChange,
)
from domain_kernel.modeling.domain.reference_packs import ReferenceDefinition, ReferencePackChange
from domain_kernel.review.domain.decisions import (
    ContentChangeAction,
    MapToDefinition,
    MapToReference,
    ReviewAction,
)


@dataclass(frozen=True, kw_only=True)
class ReviewRequirement:
    kind: RequirementKind
    code: str
    required: bool
    reference_pack: ReferencePackPin | None = None
    obligation_id: ObligationId | None = None
    # Pack requirements need exact pin + obligation ID; core/evidence require both to be None.
    # In a current snapshot, only core/evidence or matching-current-pack requirements are active.


@dataclass(frozen=True, kw_only=True)
class Question:
    id: QuestionId
    text: str
    required: bool
    scope_text: str
    obligation_id: ObligationId | None
    evidence: Sequence[Evidence]
    disposition: QuestionDisposition = QuestionDisposition.UNRESOLVED
    rationale: str | None = None
    reviewer: str | None = None
    decision_id: DecisionId | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class DecisionRecord:
    id: DecisionId
    scope: ModelScope
    case_id: ReviewCaseId
    case_version: int
    action: ReviewAction
    actor: str
    recorded_at: datetime
    proposal_ids: Sequence[ProposalId]  # Exact occurrence scope, empty for non-source decisions.
    supersedes_decision_id: (
        DecisionId | None
    )  # Only for the effects this successful correction replaces.
    applied_changes: ChangeSet  # Exact committed effects; cancellation has an empty change set.
    reference_pack_change: ReferencePackChange | None = None
    dependency_change: DependencyChange | None = None
    change_plan: ModelChangePlan | None = None  # Parent only; exact immutable authoring origin.
    group_decision_id: DecisionId | None = None  # Child -> atomic parent decision.
    member_decision_ids: Sequence[
        DecisionId
    ] = ()  # Parent -> children; do not replay effects twice.

    generated_member_case_ids: Sequence[
        ReviewCaseId
    ] = ()  # Parent's immutable submission provenance.
    released_case_ids: Sequence[
        ReviewCaseId
    ] = ()  # Parent Reject only; no child decision for a release.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReviewReceipt:
    scope: ModelScope
    case_id: ReviewCaseId
    case_version: int
    decision_id: DecisionId
    workspace_revision: int
    member_decision_ids: Sequence[DecisionId] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReviewImpact:
    changes: ChangeSet
    workspace_revision: int
    affected_case_ids: Sequence[ReviewCaseId]
    invalidated_decision_ids: Sequence[DecisionId]
    blockers: Sequence[Issue]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    @property
    def definition_changes(self) -> Sequence[DefinitionChange]: ...
    @property
    def source_alignment_changes(self) -> Sequence[SourceAlignmentChange]: ...
    @property
    def reference_disposition_changes(self) -> Sequence[ReferenceDispositionChange]: ...
    @property
    def compatibility(self) -> Compatibility: ...

    # Read-only views of the same ChangeSet; no I/O, duplicated state or additional wire fields.
    # Advisory preview; decide rechecks targets and recomputes impact atomically.
    # Reject lists parent/generated rejections and included-case releases in affected_case_ids.
    # Inspect the parent's generated_member_case_ids to distinguish these outcomes; no model effects.


@dataclass(frozen=True, kw_only=True)
class CaseDecision:
    case_id: ReviewCaseId
    expected_version: int
    decision: ContentChangeAction


@dataclass(frozen=True, kw_only=True)
class ReviewCase:
    id: ReviewCaseId
    scope: ModelScope
    run_id: DiscoveryRunId | None
    reconciliation_id: AlignmentId | None
    kind: CaseKind
    status: CaseStatus
    version: int
    evidence: Sequence[Evidence]
    definitions: Sequence[Definition]
    proposed_changes: ChangeSet
    question: Question | None
    reason: str
    proposal_ids: Sequence[ProposalId]
    correction_of_decision_id: DecisionId | None
    requirements: Sequence[ReviewRequirement]
    superseded_by_decision_id: DecisionId | None = None
    reference_pack_change: ReferencePackChange | None = None
    dependency_change: DependencyChange | None = None
    change_plan: ModelChangePlan | None = None  # Parent only; exact immutable authoring origin.
    members: Sequence[CaseDecision] = ()  # Parent stores post-reservation member versions.
    generated_member_case_ids: Sequence[ReviewCaseId] = ()
    # Immutable subset of members created by THIS submission, including new correction/remapping cases.
    # Populated by the submission service, never a caller-selected rejection policy.
    # Other members existed before grouping; their original pending proposals survive parent rejection.
    grouped_by_case_id: ReviewCaseId | None = (
        None  # Reserved leaf: direct decisions/grouping forbidden.
    )
    guarded_workspace_revision: int | None = None  # Pack/group parents: post-creation revision.

    # Pack change excludes members/dependency_change. Dependency change requires a change-set plan parent.
    # A dependency-only parent may have no members; other change-set parents require members.
    # change_plan is allowed only on a same-scope change-set parent with normalized members.
    # Generated IDs must be distinct members; non-plan groups/leaves have an empty subset.
    # Dependency-plan members are all generated. Included unsubmitted plans retain operation origins.
    # Audit never applies the plan again after its normalized member effects.
    # Original resolved case and decision remain immutable; a correction is a new case.
    @overload
    def same_as(self, *, definition: Definition, reason: str) -> MapToDefinition: ...
    @overload
    def same_as(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reason: str,
    ) -> MapToReference: ...
    def narrower_than(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reason: str,
    ) -> MapToReference: ...
    def broader_than(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reason: str,
    ) -> MapToReference: ...
    def related_to(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reason: str,
    ) -> MapToReference: ...
    def distinct_from(
        self,
        *,
        local_definition: Definition,
        reference_definition: ReferenceDefinition,
        reason: str,
    ) -> MapToReference: ...

    # Pure decision factories: no database/provider calls, automatic inference, writes or approval.
    # Source same_as(definition=...) requires SOURCE_ALIGNMENT, including reopened source corrections.
    # The two-definition same_as and other methods require REFERENCE_ALIGNMENT.
    # Reject invalid argument forms; incompatible case kinds raise InvalidDecisionError.
    # Check inspected local scope and reference association; current-state checks remain in the service.
    # Reference methods map to EQUIVALENT/NARROWER/BROADER/RELATED/DISTINCT respectively.
    # Direction is local meaning relative to reference meaning; narrower/broader are strict inclusion.
    # same_as means equivalent business meaning, not identity merging or a formal ontology assertion.
    # related_to asserts no inclusion; distinct_from asserts different meanings, not disjointness.
    # Return ordinary typed decisions for the explicit case passed to preview/decide; no auto-submit.
    def _preview(self, *, decision: ReviewAction) -> ChangeSet: ...  # Private case-local effect.
    def _decide(
        self, *, decision: ReviewAction, actor: str, expected_version: int, now: datetime
    ) -> ReviewCase: ...

    # Internal domain helpers own case-local applicability, version and status transitions.
    # Pure review/domain policies decide coordinated effects from captured model/case/decision state:
    # group acceptance/rejection, generated-member rejection vs included-member release,
    # correction/supersession and dependent invalidation/re-review. No repository/service arguments.
    # Return immutable effects; application services load/recheck current state and commit them atomically.
    # Coordinated policies verify effective decisions and occurrence scope; overlapping corrections fail.
    # Incompatible/undetermined dependents become stale and open required re-review cases.
    # Preserve unaffected occurrence mappings when a source decision is partially superseded.
    # Group Accept checks parent/member guards and validates one prospective graph.
    # Parent Reject rejects generated members and releases pre-existing members with new versions.
    # Dependency-plan members are all generated; obsolete target guards do not prevent cancellation.
    # Dependency-parent Accept replaces pins and repairs together; historical closures stay separate.
    # Pack acceptance supersedes generated pending/deferred old-pack-only cases/unresolved questions.
    # Resolved/reviewed history and core/evidence/manual work survive; derive current-pack requirements.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReviewSnapshot:
    scope: ModelScope
    version: int
    content_hash: ContentHash
    decisions: Sequence[DecisionRecord]
    pending_required: int
    questions: Sequence[Question]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # pending_required counts active unresolved core/evidence/current-pack requirements only.
    # Superseded cases/questions never count, even if their historical required flag was True.
    # Resolved/reviewed old-pack-only history stays intact but supplies no current exceptions.
```

```python
# src/domain_kernel/review/application/service.py
from __future__ import annotations

from domain_kernel._shared.domain.authoring import ModelChangePlan

from domain_kernel._shared.domain.enums import (
    CaseKind,
    CaseStatus,
)

from collections.abc import Sequence

from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.page_cursor import PageCursor

from typing import Annotated, Protocol

from domain_kernel._shared.domain.contracts import Page
from domain_kernel.review.domain.decisions import ReviewAction
from domain_kernel.review.domain.models import (
    CaseDecision,
    DecisionRecord,
    ReviewCase,
    ReviewImpact,
    ReviewReceipt,
)
from pydantic import Field

type ReviewDecision = Annotated[ReviewAction, Field(discriminator="kind")]


class Review(Protocol):
    async def list(
        self,
        *,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
        kind: CaseKind | None = None,
        status: CaseStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ReviewCase]: ...
    async def get(self, *, case_id: ReviewCaseId) -> ReviewCase: ...
    async def propose_plan(
        self, *, actor: str, plan: ModelChangePlan, idempotency_key: str | None = None
    ) -> ReviewCase: ...
    # Client-owned application transaction: validate all, create leaves, reserve members, create parent.
    # Reuse proposal/reopen/group domain rules inside ONE transaction, not sequential public calls.
    # Reload and compare full bound/edited snapshots, scope, workspace/case/definition versions.
    # New IDs reserve unchanged; conflicting IDs/overlapping corrections/pack-change reservations fail.
    # No partial writes on failure. One workspace advance; parent guards post-creation revision.
    # Newly authored steps propose member Accept actions; no review decision is recorded yet.
    # Included pending cases always carry caller-chosen actions. Parent stores exact plan/guard/member versions.
    # Plan ID independently binds canonical payload/parent within scope; caller keys are extra replay keys.
    # Default key is plan ID. Replay before stale checks; changed payload or submitter conflicts.
    # Bind the original actor alongside the plan payload, including for replay through a different key.
    # Unique (scope, plan_id) at persistence; concurrent identical losers rollback then replay the winner.
    # Dependency plans verify/materialize old/new closures and store DependencyChange on the parent.
    # They allow only local revisions/retirements; synthesize remapped revision leaves for untouched owners.
    # Parent Accept applies pins + all members atomically; blocks unresolved prospective references.
    # Persist generated_member_case_ids for all new leaves (including corrections/synthetic remappings).
    # Parent Reject atomically rejects generated members and releases pre-existing included cases.
    # Record Reject decisions only for parent/generated cases; release advances included case versions.
    # Rejected never-approved creations release pending name reservations, never their historical IDs.
    # No proposed content/action is applied and prior effective decisions remain intact.
    # Dependency plans have only generated members, so rejection leaves none pending individually.
    async def propose_change_set(
        self,
        *,
        actor: str,
        decisions: Sequence[CaseDecision],
        expected_workspace_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # Nonempty, same-model pending content/alignment leaf cases only; no nested/pack/question cases.
    # Check workspace/case versions and actions; reserve members with advanced case versions.
    # Parent records reserved versions and guard AFTER creation's own workspace increment.
    # Preview validates combined final state, including reserved IDs from new/restored definitions.
    # Contradictory writes, duplicate effects and unresolved affected references are rejected.
    # No member effects applied on proposal; no direct member decisions while reserved.
    # Parent Accept applies all members in one transaction and advances workspace once.
    # These members all pre-exist grouping: generated_member_case_ids is empty.
    # Parent Reject releases members with new versions and records no rejection on their behalf.
    # Current inspected case version is required even when the workspace/targets are stale.
    # Whole-workspace staleness rejects Accept; discard/regroup after inspection instead.
    # Reject group creation while a pack-change case is pending (transactional exclusion).
    async def reopen(
        self,
        *,
        actor: str,
        case_id: ReviewCaseId,
        expected_version: int,
        reason: str,
        proposal_ids: Sequence[ProposalId] | None = None,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # New pending case linked to the still-effective decision; never mutate old case/history.
    # None targets the full interpretation effect of a source/reference/question/confirmation case.
    # Nonempty proposal_ids targets only source mappings, including those from proposal Accept;
    # returns a source_alignment case and leaves definition approval/content/lifecycle untouched.
    # Without explicit source selection, reopening a definition-lifecycle case is invalid.
    # Reject targets already superseded or with overlapping pending corrections; stale -> error.
    # New required case blocks publication; prior effect remains until correction is accepted.
    # Reject on a correction cancels it, with supersedes_decision_id=None; original effect remains.
    # Cancellation uses current case version, not obsolete target revisions; required gaps remain.
    # Definition lifecycle changes use revision/retirement/restoration proposals instead.
    # Do not reopen group/pack parents or superseded cases; use current cases/member decisions.
    # For pack corrections, propose a new explicit pack change.
    async def preview(self, *, case: ReviewCase, decision: ReviewDecision) -> ReviewImpact: ...
    async def decide(
        self,
        *,
        case: ReviewCase,
        decision: ReviewDecision,
        actor: str,
        idempotency_key: str | None = None,
    ) -> ReviewReceipt: ...
    # Both calls derive identity/scope/version from the inspected case; validate against stored state.
    # Never trust caller-modified case content or silently substitute a newer version.
    # Preview is read-only; decide reloads/rechecks atomically, subject to stored idempotent replay.
    # Matching retries replay before stale checks; changed request content under a key conflicts.
    # Accept checks relevant workspace/target guards; Reject may cancel obsolete target intent.
    # Reject still requires the current case/member versions and intact parent reservations.
    async def history(
        self, *, case_id: ReviewCaseId, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[DecisionRecord]: ...
```

```python
# src/domain_kernel/review/application/ports.py
from __future__ import annotations

from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId

from domain_kernel._shared.domain.enums import (
    CaseKind,
    CaseStatus,
)

from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.page_cursor import PageCursor

from typing import Protocol

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.domain.contracts import ModelScope, Page
from domain_kernel.discovery.api.discovery import DiscoveryDraft
from domain_kernel.reconciliation.api.reconciliation import Alignment
from domain_kernel.review.domain.models import (
    DecisionRecord,
    ReviewCase,
    ReviewSnapshot,
)


class CaseFactory(Protocol):
    def from_discovery(
        self, *, draft: DiscoveryDraft, alignment: Alignment
    ) -> tuple[ReviewCase, ...]: ...


class ReviewRepository(Protocol):
    async def get_by_plan(
        self, *, scope: ModelScope, plan_id: ChangePlanId
    ) -> ReviewCase | None: ...
    # Case persistence uniquely binds non-null parent change_plan.id within scope to payload/parent.
    # Never overwrite that binding; same canonical plan replays, changed payload conflicts.
    # All case/reservation/plan-binding/workspace writes commit or roll back in one transaction.
    async def get(self, *, scope: ModelScope, case_id: ReviewCaseId) -> ReviewCase: ...
    async def add(self, *, case: ReviewCase) -> None: ...
    async def list(
        self,
        *,
        scope: ModelScope,
        run_id: DiscoveryRunId | None,
        reconciliation_id: AlignmentId | None,
        kind: CaseKind | None,
        status: CaseStatus | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[ReviewCase]: ...
    async def save(self, *, case: ReviewCase, expected_version: int) -> None: ...
    async def append_decision(self, *, record: DecisionRecord) -> None: ...
    async def history(
        self, *, scope: ModelScope, case_id: ReviewCaseId, limit: int, cursor: PageCursor | None
    ) -> Page[DecisionRecord]: ...
    async def snapshot(self, *, scope: ModelScope) -> ReviewSnapshot: ...

    # Persistence guarantees for application-coordinated domain effects; not repository business logic.
    # ReviewCase and pure review-domain policies decide applicability, releases and re-review effects.
    # Repositories do not derive decisions or create correction/invalidation cases independently.
    # CAS case + append decision + update definitions/alignment/workspace revision + outcome:
    # one short transaction; stale/cross-model commands rejected before any mutation.
    # Group creation reserves member cases atomically; at most one parent reservation per leaf.
    # Resolve leaves + parent, append linked audits, apply effects/re-review, revision/outcome: one txn.
    # Parent/generated rejection records, releases, reservation removal and receipt commit atomically.
    # Advance workspace once; matching retries return the stored receipt without advancing it again.
    # Never record child Reject decisions for released cases; no partial outcome on failure.
    # Persist accepted dependency pins and coordinated repairs in the same transaction.
    # Pack Accept stores new pin, revised alignments, invalidation cases and audit in the same txn.
    # Only one pending pack-change case per scope; exclude simultaneous pending group reservations.
    # Persist policy-determined supersession versions/audit and new current-pack cases atomically.


class ReviewTransaction(Transaction, Protocol):
    @property
    def reviews(self) -> ReviewRepository: ...
```

```python
# src/domain_kernel/review/api/review.py
from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.sources.api.sources import IngestedSource
from domain_kernel.review.application.service import Review, ReviewDecision
from domain_kernel.review.domain.decisions import (
    Accept,
    AnswerQuestion,
    ApproveLocalExtension,
    Confirmation,
    ConfirmStatement as _ConfirmStatement,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    MapToDefinition,
    MapToReference,
    Reject,
)
from domain_kernel.review.domain.models import (
    DecisionRecord,
    CaseDecision,
    Question,
    ReviewCase,
    ReviewImpact,
    ReviewReceipt,
    ReviewRequirement,
    ReviewSnapshot,
)


@dataclass(frozen=True, kw_only=True)
class ConfirmStatement(_ConfirmStatement):
    # SDK-boundary convenience over the same immutable domain command; no extra fields/wire kind.
    @classmethod
    def from_statement(
        cls, *, source: IngestedSource, authority: str, reason: str
    ) -> ConfirmStatement:
        return cls._from_statement(
            revision=source.revision,
            evidence=source.evidence,
            authority=authority,
            reason=reason,
        )

    # Domain logic accepts the base command; codecs preserve its payload/discriminator.
    # Public decoding restores this facade for the same public construction surface.
    # Adapt captured values only; validation and attribution rules remain in the domain helper.


__all__ = [
    "Review",
    "ReviewDecision",
    "Accept",
    "AnswerQuestion",
    "ApproveLocalExtension",
    "ConfirmStatement",
    "Defer",
    "EditDefinition",
    "Exclude",
    "KeepNonblockingQuestion",
    "MapToDefinition",
    "MapToReference",
    "Reject",
    "Confirmation",
    "DecisionRecord",
    "CaseDecision",
    "Question",
    "ReviewCase",
    "ReviewImpact",
    "ReviewReceipt",
    "ReviewRequirement",
    "ReviewSnapshot",
]
```

```python
# src/domain_kernel/modeling/domain/reference_packs.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.model_values import Terminology

from domain_kernel._shared.domain.enums import (
    ObligationKind,
    PackMaturity,
    ReferenceAssetKind,
)

from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.content_hash import ContentHash


from domain_kernel._shared.domain.ontology_assets import OntologyClosure, OntologyTermReference
from dataclasses import dataclass
from typing import Literal

from domain_kernel._shared.domain.contracts import Issue, ReferencePackPin
from domain_kernel._shared.domain.definitions import DefinitionBody
from domain_kernel._shared.domain.ontology import OntologyStatement


@dataclass(frozen=True, kw_only=True)
class ReferenceOrigin:
    reference_pack: ReferencePackPin
    definition_id: ReferenceDefinitionId  # Original identity before composition namespacing.


@dataclass(frozen=True, kw_only=True)
class ReferenceDefinition:
    id: ReferenceDefinitionId
    name: str
    meaning: str
    body: DefinitionBody
    provenance: str
    origins: Sequence[ReferenceOrigin] = ()
    ontology_terms: Sequence[OntologyTermReference] = ()
    terminology: Terminology = Terminology()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.
    @property
    def reference_pack(self) -> ReferencePackPin | None: ...

    # Read-only upstream meaning, including its qualifications; a changed meaning requires a local identity.
    # Body references use ReferenceDefinitionId within the materialized pack graph, never model pins.
    # Containing-pack runtime context, as for Pattern: None before materialization; not a wire field.
    # Loaded/composed packs associate immutable definitions (including pattern members) with their pin.
    # ReferenceOrigin preserves upstream lineage separately; composition selects the containing pin.


@dataclass(frozen=True, kw_only=True)
class ReferencePackDependency:
    key: str
    version: str
    content_hash: ContentHash
    kind: ReferenceAssetKind
    provenance: str
    license: str


@dataclass(frozen=True, kw_only=True)
class ReferencePackObligation:
    id: ObligationId
    description: str
    kind: ObligationKind
    required: bool
    reference_ids: Sequence[ReferenceDefinitionId]
    validator_id: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True, init=False)
class Pattern:
    id: PatternId
    name: str
    display_name: str
    definitions: tuple[ReferenceDefinition, ...]  # A closed reference graph.
    entrypoint_ids: tuple[ReferenceDefinitionId, ...]
    description: str

    def __init__(
        self,
        *,
        definitions: Sequence[ReferenceDefinition],
        entrypoint_ids: Sequence[ReferenceDefinitionId],
        description: str,
        display_name: str | None = None,
        name: str | None = None,
    ) -> None: ...
    @property
    def reference_pack(self) -> ReferencePackPin | None: ...

    # Generate an independent ID once; resolve display_name/name using the shared naming rules.
    # Copy/freeze sequences. Pack validation rejects duplicate pattern names/IDs; no suffixes.
    # Codecs preserve stored IDs/names rather than invoking authoring defaults on reconstruction.
    # reference_pack is read-only runtime context: None on a standalone authored pattern.
    # A materialized pack exposes immutable pattern copies associated with its exact pin.
    # This context is not an embedded wire field (avoids a self-referential pack content hash).


@dataclass(frozen=True, kw_only=True)
class DefinitionBinding:
    reference_id: ReferenceDefinitionId
    definition_id: DefinitionId
    definition_revision: int


@dataclass(frozen=True, kw_only=True)
class ReferencePackImportManifest:
    reference_pack: ReferencePackPin
    namespace: str
    pattern_ids: Sequence[PatternId]
    obligation_ids: Sequence[ObligationId]
    omitted_obligations: Sequence[ReferencePackObligation]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Complete original snapshots, before namespacing; preserve requiredness and validator.
    # They are historical metadata, not active obligations; warnings survive dump/load.


@dataclass(frozen=True, kw_only=True)
class ReferencePackComposition:
    imports: Sequence[ReferencePackImportManifest]
    actor: str  # Host-attributed author, not SDK-authenticated authority.
    reason: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReferencePack:
    pin: ReferencePackPin
    title: str
    applicability: str
    exclusions: Sequence[str]
    maturity: PackMaturity
    provenance: str
    license: str
    # Selected dependency closure is materialized below; manifests never trigger runtime imports.
    definitions: Sequence[ReferenceDefinition]
    dependencies: Sequence[ReferencePackDependency]
    obligations: Sequence[ReferencePackObligation]
    supported_semantics: Sequence[str]  # Registered capability/version identifiers.
    # Registered capability declarations, not a guarantee that optional validators are installed.
    # Unknown required semantics fail; optional unsupported constructs produce Issues.
    semantic_mapping_version: str
    patterns: Sequence[Pattern] = ()
    ontology_statements: Sequence[OntologyStatement] = ()
    ontologies: Sequence[OntologyClosure] = ()
    composition: ReferencePackComposition | None = None
    schema_version: Literal["1.0"] = "1.0"
    format: Literal["domain-kernel.reference-pack"] = "domain-kernel.reference-pack"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    @classmethod
    def compose(cls, *, spec: ReferencePackSpec, actor: str, reason: str) -> ReferencePackBuild: ...
    def validate(self) -> ReferencePackValidation: ...
    def serialize(self) -> bytes: ...
    @classmethod
    def deserialize(
        cls,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> ReferencePack: ...
    @classmethod
    def get_json_schema(cls, *, schema_version: str = "1.0") -> str: ...

    # Delegate through the SDK boundary to the existing composer/strict codec; domain imports stay stdlib-only.
    # No Client, database, catalog lookup, transport, writes or approval. No standalone public aliases.
    # Keep ReferencePackBuild diagnostics, canonical bytes, schema/hash checks and payload limits unchanged.
    # Schema access supports registered versions only; missing/unsupported semantic mappings fail explicitly.
    def get_pattern(
        self, *, name: str | None = None, pattern_id: PatternId | None = None
    ) -> Pattern: ...

    # Exactly one selector; exact unique name/ID within this materialized pack, no I/O.
    # Never search display labels, aliases or external dependencies. Missing -> PatternNotFoundError.
    # Returned immutable content is associated with self.pin, as are items in self.patterns.


@dataclass(frozen=True, kw_only=True)
class ReferencePackImport:
    reference_pack: ReferencePack  # Already loaded and hash-verified; no implicit I/O.
    namespace: str  # Unique; matches [A-Za-z][A-Za-z0-9_-]*.
    # Imported definition/pattern/obligation ID values = namespace + ":" + original_id.value.
    # Pattern names/display names stay unchanged; duplicate names in the result fail validation.
    # Body-local attributes/roles/activity/flow/condition IDs keep their original local scope.
    pattern_ids: Sequence[PatternId] = ()  # No patterns selected by default.
    obligation_ids: Sequence[ObligationId]  # Selected obligations retain requiredness/validator.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReferencePackSpec:
    key: str
    version: str
    title: str
    applicability: str
    exclusions: Sequence[str] = ()
    maturity: PackMaturity = PackMaturity.EXPERIMENTAL
    provenance: str
    license: str
    semantic_mapping_version: str = "1.0"
    supported_semantics: Sequence[str] = ()  # Additional local declarations.
    imports: Sequence[ReferencePackImport] = ()
    definitions: Sequence[ReferenceDefinition] = ()
    patterns: Sequence[Pattern] = ()
    obligations: Sequence[ReferencePackObligation] = ()
    dependencies: Sequence[ReferencePackDependency] = ()
    ontology_statements: Sequence[OntologyStatement] = ()
    ontologies: Sequence[OntologyClosure] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReferencePackValidation:
    valid: bool
    issues: Sequence[Issue]
    required_capabilities: Sequence[str]  # Adoption checks installed capabilities separately.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReferencePackBuild:
    pack: ReferencePack | None  # None on composition errors; warnings may accompany a valid pack.
    validation: ReferencePackValidation


@dataclass(frozen=True, kw_only=True)
class ReferencePackChange:
    before: ReferencePack | None  # None denotes absence, never a synthetic/local pack.
    after: (
        ReferencePack | None
    )  # Attach, replace or explicitly remove; both None is an invalid no-op.
    added_obligation_ids: Sequence[ObligationId]
    removed_obligation_ids: Sequence[ObligationId]
    changed_obligation_ids: Sequence[ObligationId]
    affected_definition_ids: Sequence[DefinitionId]
    superseded_case_ids: Sequence[ReviewCaseId]  # Pending/deferred generated old-pack-only work.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Compare obligations by explicit ID, never guessed name equivalence.
    # The accompanying ChangeSet records full applied definition/alignment effects.
```

```python
# src/domain_kernel/modeling/domain/semantics.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from enum import StrEnum, unique
from domain_kernel._shared.domain.contracts import Issue
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel._shared.domain.ontology import Iri, OntologyStatement
from domain_kernel._shared.domain.ontology_assets import (
    OntologyClosure,
    OntologySyntax,
    OntologyTermReference,
    OntologyLimits,
)


@unique
class ReasoningProfile(StrEnum):
    RDFS = "rdfs"
    OWL2_EL = "owl2_el"
    OWL2_QL = "owl2_ql"
    OWL2_RL = "owl2_rl"
    OWL2_DL = "owl2_dl"
    OWL2_FULL = "owl2_full"


@unique
class SemanticRegime(StrEnum):
    RDFS = "rdfs"
    OWL_DIRECT = "owl_direct"
    OWL_RDF = "owl_rdf"


@unique
class ReasoningTask(StrEnum):
    CONSISTENCY = "consistency"
    CLASSIFICATION = "classification"
    ENTAILMENT = "entailment"


@unique
class SemanticStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    FAILED = "failed"


@unique
class ModuleExtractionMethod(StrEnum):
    BOT = "bot"
    TOP = "top"
    STAR = "star"
    MIREOT = "mireot"


@unique
class ModuleGuarantee(StrEnum):
    SIGNATURE_ENTAILMENTS = "signature_entailments"
    NONE = "none"


@dataclass(frozen=True, kw_only=True)
class ReasoningSupport:
    profile: ReasoningProfile
    regime: SemanticRegime
    task: ReasoningTask
    complete: bool
    restrictions: Sequence[str] = ()  # Registered capability restrictions, not guessed fallbacks.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ModuleExtractionSupport:
    method: ModuleExtractionMethod
    profile: ReasoningProfile
    regime: SemanticRegime
    guarantee: ModuleGuarantee


@dataclass(frozen=True, kw_only=True)
class OntologyCapabilities:
    adapter_id: str
    adapter_version: str
    parse_syntaxes: Sequence[OntologySyntax] = ()
    serialize_syntaxes: Sequence[OntologySyntax] = ()
    reasoning: Sequence[ReasoningSupport] = ()
    extraction: Sequence[ModuleExtractionSupport] = ()
    datatypes: Sequence[Iri] = ()
    feature_ids: Sequence[str] = ()  # Versioned open extension capability IDs.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReasoningRequest:
    profile: ReasoningProfile
    regime: SemanticRegime
    task: ReasoningTask
    signature: Sequence[OntologyTermReference] = ()
    query: OntologyClosure | None = None

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Query required only for ENTAILMENT; signature selects named classification targets.
    # Empty signature means all named input classes; never all possible/infinite entailed triples.


@dataclass(frozen=True, kw_only=True)
class ReasoningResult:
    input_hash: ContentHash
    request: ReasoningRequest
    adapter: OntologyCapabilities
    fingerprint: str  # Request + engine + versions + limits + mapping + exact closure.
    limits: OntologyLimits
    status: SemanticStatus
    consistent: bool | None
    entailed: bool | None
    unsatisfiable: Sequence[OntologyTermReference]
    inferred: Sequence[OntologyStatement]
    issues: Sequence[Issue]
    explanations: Sequence[str] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # None is unknown/not requested, never false. No entailment conclusion from inconsistent inputs.
    # Inferences have separate provenance; they never mutate assertions or approve model changes.


@dataclass(frozen=True, kw_only=True)
class OntologyModuleResult:
    source_hash: ContentHash
    fingerprint: str  # Inputs, selected graphs, seeds, method, regime/profile, adapter and limits.
    limits: OntologyLimits
    seeds: Sequence[OntologyTermReference]
    method: ModuleExtractionMethod
    profile: ReasoningProfile
    regime: SemanticRegime
    adapter: OntologyCapabilities
    status: SemanticStatus
    guarantee: ModuleGuarantee
    signature: Sequence[OntologyTermReference]
    ontology: OntologyClosure | None
    issues: Sequence[Issue]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # New ontology identity, original term IRIs; guarantee only for documented supported regime.
    # Incomplete/unsupported results have no usable ontology. MIREOT always has guarantee NONE.
```

```python
# src/domain_kernel/modeling/application/ontology.py
from __future__ import annotations

from collections.abc import Sequence

from typing import Protocol
from domain_kernel._shared.domain.ontology import Iri
from domain_kernel._shared.domain.ontology_assets import (
    OntologyClosure,
    OntologyDocument,
    OntologyLimits,
    OntologySyntax,
    OntologyTermReference,
    ParsedOntology,
)
from domain_kernel.modeling.domain.semantics import (
    ModuleExtractionMethod,
    OntologyCapabilities,
    OntologyModuleResult,
    ReasoningRequest,
    ReasoningResult,
    ReasoningProfile,
    SemanticRegime,
)


class OntologyAdapter(Protocol):
    @property
    def capabilities(self) -> OntologyCapabilities: ...
    def parse(
        self,
        *,
        document: OntologyDocument,
        resources: Sequence[OntologyDocument],
        limits: OntologyLimits,
    ) -> ParsedOntology: ...
    def serialize(
        self,
        *,
        ontology: ParsedOntology,
        syntax: OntologySyntax,
        document_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyDocument: ...

    # Preserve complete supported syntax; named graphs cannot be flattened into a graph-only format.
    # No import fetches; contexts resolve only from exact supplied resources. No executable extensions.


class OntologyReasoner(Protocol):
    @property
    def capabilities(self) -> OntologyCapabilities: ...
    async def reason(
        self,
        *,
        ontology: OntologyClosure,
        request: ReasoningRequest,
        limits: OntologyLimits,
    ) -> ReasoningResult: ...


class OntologyModuleExtractor(Protocol):
    @property
    def capabilities(self) -> OntologyCapabilities: ...
    async def extract(
        self,
        *,
        ontology: OntologyClosure,
        seeds: Sequence[OntologyTermReference],
        method: ModuleExtractionMethod,
        profile: ReasoningProfile,
        regime: SemanticRegime,
        ontology_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyModuleResult: ...

    # Application owns process/service lifecycle; cancellation/limits must stop work and bound output.
```

```python
# src/domain_kernel/ontologies.py
from __future__ import annotations

from collections.abc import Sequence
from domain_kernel.modeling.application.ontology_validation import ReasoningModelValidator
from domain_kernel._shared.domain.ontology import Iri
from domain_kernel._shared.domain.ontology_assets import (
    OntologyClosure,
    OntologyDocument,
    OntologyLimits,
    OntologyTermReference,
)
from domain_kernel.modeling.application.ontology import (
    OntologyAdapter,
    OntologyModuleExtractor,
    OntologyReasoner,
)
from domain_kernel.modeling.domain.semantics import (
    ModuleExtractionMethod,
    OntologyModuleResult,
    ReasoningRequest,
    ReasoningResult,
    ReasoningProfile,
    SemanticRegime,
)


def load_ontology(
    *,
    document: OntologyDocument,
    resources: Sequence[OntologyDocument] = (),
    adapter: OntologyAdapter | None = None,
    limits: OntologyLimits | None = None,
) -> OntologyClosure: ...


async def reason_ontology(
    *,
    ontology: OntologyClosure,
    request: ReasoningRequest,
    reasoner: OntologyReasoner,
    limits: OntologyLimits | None = None,
) -> ReasoningResult: ...


async def extract_ontology_module(
    *,
    ontology: OntologyClosure,
    seeds: Sequence[OntologyTermReference],
    method: ModuleExtractionMethod,
    profile: ReasoningProfile,
    regime: SemanticRegime,
    ontology_iri: Iri,
    extractor: OntologyModuleExtractor,
    limits: OntologyLimits | None = None,
) -> OntologyModuleResult: ...


# Pure input transport; no Client, database, hidden downloads or automatic approval.
# Default parser is lazy RDFLib for advertised syntaxes; other syntaxes need an explicit adapter.
# Invalid bytes/headers/aliases/missing dependencies -> InvalidOntologyError; missing adapter extra
# -> MissingDependencyError; unsupported parsing/serialization -> UnsupportedCapabilityError.
# Semantic operations return typed non-success results, never a successful partial interpretation.
# Snapshot input Sequences; validate hashes/closure/limits, requested capability and returned pins.
# Repeated imports use visited pins, allow cycles, reject ambiguous requested aliases or hash substitution.
# Different explicitly requested version IRIs may coexist; semantic consequences are diagnosed by adapters.
```

```python
# src/domain_kernel/modeling/domain/composition.py
from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass
from enum import StrEnum, unique
from domain_kernel._shared.domain.contracts import Issue, ModelVersion, PinnedDefinitionReference
from domain_kernel._shared.domain.definitions import Definition
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.modeling.domain.models import DomainModelBundle
from domain_kernel.modeling.domain.reference_packs import ReferencePack
from domain_kernel._shared.domain.ontology_assets import OntologyClosure


@unique
class TraversalDirection(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


@dataclass(frozen=True, kw_only=True)
class ModelComposition:
    roots: Sequence[ModelVersion]
    bundles: Sequence[DomainModelBundle]  # Unique exact transitive closure; original approvals.
    content_hash: ContentHash

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Read-only same-project assembly, not a new approved model or logical union.


@dataclass(frozen=True, kw_only=True)
class SliceDefinition:
    reference: PinnedDefinitionReference
    definition: Definition


@dataclass(frozen=True, kw_only=True)
class ModelSlice:
    composition_hash: ContentHash
    models: Sequence[ModelVersion]
    seeds: Sequence[PinnedDefinitionReference]
    selected: Sequence[SliceDefinition]
    support: Sequence[SliceDefinition]
    reference_packs: Sequence[ReferencePack]
    ontologies: Sequence[OntologyClosure]
    max_hops: int
    direction: TraversalDirection
    content_hash: ContentHash
    issues: Sequence[Issue]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Selected + support close typed references; preserve original versions/identities/provenance.
    # Not an OWL locality module, permission filter, complete source bundle or new approval.
```

```python
# src/domain_kernel/composition.py
from __future__ import annotations

from collections.abc import Sequence
from domain_kernel._shared.domain.contracts import PinnedDefinitionReference
from domain_kernel.modeling.domain.models import DomainModelBundle
from domain_kernel.modeling.domain.composition import (
    ModelComposition,
    ModelSlice,
    TraversalDirection,
)


def compose_models(
    *,
    bundles: Sequence[DomainModelBundle],
    max_bytes: int = 64 * 1024 * 1024,
) -> ModelComposition: ...


def slice_model(
    *,
    composition: ModelComposition,
    seeds: Sequence[PinnedDefinitionReference],
    max_hops: int = 0,
    direction: TraversalDirection = TraversalDirection.BOTH,
    max_definitions: int = 10_000,
    max_bytes: int = 64 * 1024 * 1024,
) -> ModelSlice: ...


# Supplied published bundles only; verify hashes/approval bindings, no producer state/I/O.
# Empty roots/seeds, unknown/stale references, negative hops or nonpositive limits fail explicitly.
# Distinct versions of one model conflict; never union history, drafts or different projects.
# Selection follows typed references in the specified direction for max_hops, then closes required
# outgoing references without truncation. A selected semantic module keeps its full closure.
# Exceeding bytes/definition limits -> ResourceLimitError; neither helper mutates source models.
```

```python
# src/domain_kernel/modeling/domain/models.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.dependencies import DependencyChangeRequest
from domain_kernel._shared.domain.acceptance import AcceptanceCheckResult

from domain_kernel._shared.domain.authoring import ModelChangePlan
from domain_kernel.modeling.domain.semantics import ReasoningResult

from domain_kernel._shared.domain.enums import (
    ModelKind,
    ReviewActionKind,
)

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.content_hash import ContentHash


from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from domain_kernel._shared.domain.contracts import (
    Issue,
    ModelScope,
    ModelVersion,
    ReferencePackPin,
    SourceRevision,
)
from domain_kernel._shared.domain.definitions import (
    ChangeSet,
    Concept,
    Definition,
    ReferenceDisposition,
    SourceAlignment,
)
from domain_kernel._shared.domain.ontology import OntologyStatement
from domain_kernel._shared.domain.proposals import Proposal
from domain_kernel._shared.domain.review import ReviewAction
from domain_kernel.modeling.domain.reference_packs import ReferencePack, ReferencePackChange

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment, ProjectionRequest


@dataclass(frozen=True, kw_only=True)
class DependencyChange:
    request: DependencyChangeRequest
    before_bundles: Sequence[DomainModelBundle]
    after_bundles: Sequence[DomainModelBundle]
    affected_definition_ids: Sequence[DefinitionId]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Materialized closures at their exact historical contexts, never unioned with active dependencies.


@dataclass(frozen=True, kw_only=True)
class ModelInfo:
    scope: ModelScope
    name: str
    display_name: str
    kind: ModelKind
    description: str
    reference_pack: ReferencePackPin | None
    revision: int
    baseline: ModelVersion | None
    dependencies: Sequence[ModelVersion]
    created_at: datetime

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class VisibleQuestion:
    id: QuestionId
    text: str
    scope_text: str
    rationale: str
    reviewer: str
    decision_id: DecisionId


@dataclass(frozen=True, kw_only=True)
class ReviewAudit:
    decision_id: DecisionId
    case_id: ReviewCaseId
    actor: str
    action_kind: ReviewActionKind
    reason: str
    recorded_at: datetime
    # Full typed decision payloads, including confirmations, retained in Candidate.decisions.


@dataclass(frozen=True, kw_only=True)
class ModelContent:
    definitions: Sequence[Definition]  # Active approved definitions only.
    retired_definitions: Sequence[Definition]  # Tombstones and explicit replacement lineage.
    source_alignments: Sequence[SourceAlignment]
    reference_dispositions: Sequence[ReferenceDisposition]
    ontology_statements: Sequence[OntologyStatement] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Candidate:
    id: CandidateId
    scope: ModelScope
    kind: ModelKind
    description: str
    reference_pack: ReferencePackPin | None
    workspace_revision: int
    review_snapshot_version: int
    content_hash: ContentHash  # Canonical scope/kind/description/pack/content/evidence/decisions/baseline snapshot.
    content: ModelContent
    sources: Sequence[SourceRevision]
    proposals: Sequence[Proposal]  # Materialize occurrences targeted by source alignments.
    baseline: ModelVersion | None
    dependencies: Sequence[ModelVersion]
    dependency_bundles: Sequence[DomainModelBundle]  # Exact direct pins, recursively complete.
    review_audit: Sequence[ReviewAudit]
    decisions: Sequence[DecisionSnapshot]
    nonblocking_questions: Sequence[VisibleQuestion]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class DecisionSnapshot:
    id: DecisionId
    scope: ModelScope
    case_version: int
    case_id: ReviewCaseId
    action: ReviewAction  # Complete immutable typed decision, including confirmations.
    actor: str
    recorded_at: datetime
    proposal_ids: Sequence[ProposalId]
    supersedes_decision_id: DecisionId | None
    applied_changes: ChangeSet
    reference_pack_change: ReferencePackChange | None = None
    dependency_change: DependencyChange | None = None
    change_plan: ModelChangePlan | None = None  # Parent only; exact immutable authoring origin.
    group_decision_id: DecisionId | None = None
    member_decision_ids: Sequence[DecisionId] = ()

    generated_member_case_ids: Sequence[
        ReviewCaseId
    ] = ()  # Parent's immutable submission provenance.
    released_case_ids: Sequence[
        ReviewCaseId
    ] = ()  # Parent Reject only; no child decision for a release.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ValidationReport:
    id: ValidationReportId
    scope: ModelScope
    candidate_id: CandidateId
    candidate_hash: ContentHash
    validator_fingerprint: str
    reference_pack: ReferencePackPin | None
    issues: Sequence[Issue]
    reasoning: Sequence[ReasoningResult] = ()
    acceptance: Sequence[AcceptanceCheckResult] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class ReadinessCheck:
    code: str
    passed: bool
    required: bool
    resource_labels: Sequence[
        str
    ]  # Diagnostic display labels only, never accepted as typed lookup IDs.
    message: str

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class Readiness:
    scope: ModelScope
    candidate_id: CandidateId
    candidate_hash: ContentHash
    ready: bool
    checks: Sequence[ReadinessCheck]
    blockers: Sequence[Issue]
    nonblocking_questions: Sequence[VisibleQuestion]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Closure != business truth. Required model evidence/confirmation/reference_pack gaps always block.


@dataclass(frozen=True, kw_only=True)
class PublicationRules:
    allow_reviewed_nonblocking_questions: bool


@dataclass(frozen=True, kw_only=True)
class Publication:
    id: PublicationId
    scope: ModelScope
    candidate: Candidate
    reference_pack: (
        ReferencePack | None  # Exact selected pack, or None; no hidden local-pack substitution.
    )
    validation: ValidationReport
    readiness: Readiness
    changes: ChangeSet
    # Rules + validator/version registry; changed capabilities require prepare_publication again.
    policy_fingerprint: str
    prepared_at: datetime

    # Snapshot-local views of stored readiness; no I/O, copies, recomputation or separate state.
    @property
    def ready(self) -> bool: ...
    @property
    def checks(self) -> tuple[ReadinessCheck, ...]: ...
    @property
    def blockers(self) -> tuple[Issue, ...]: ...
    @property
    def nonblocking_questions(self) -> tuple[VisibleQuestion, ...]: ...

    # Persist even when blocked. Never silently replace this snapshot with the latest one.
    # Readiness remains the serialized backing record; direct properties add no wire fields.


@dataclass(frozen=True, kw_only=True)
class Approval:
    # Immutable release authorization constructed internally after publish checks and retained in its bundle.
    id: ApprovalId
    scope: ModelScope
    publication_id: PublicationId
    candidate_id: CandidateId
    candidate_hash: ContentHash
    validation_id: ValidationReportId
    workspace_revision: int
    review_snapshot_version: int
    policy_fingerprint: str
    actor: str
    reason: str
    approved_at: datetime


@dataclass(frozen=True, kw_only=True)
class DomainModelBundle:
    id: BundleId
    scope: ModelScope
    version: str
    schema_version: Literal["1.0"]
    semantic_mapping_version: str
    publication: (
        Publication  # Exact content + reference_pack + provenance + decisions + visible exceptions.
    )
    approval: Approval
    content_hash: ContentHash
    published_at: datetime
    format: Literal["domain-kernel.bundle"] = "domain-kernel.bundle"

    @property
    def model_version(self) -> ModelVersion: ...
    @property
    def kind(self) -> ModelKind: ...  # Approval never changes proposed -> observed.
    @property
    def description(self) -> str: ...  # Exact publication.candidate.description.
    @property
    def content(self) -> ModelContent: ...
    def get_concept(
        self, *, name: str | None = None, concept_id: DefinitionId | None = None
    ) -> Concept: ...

    # Exactly one selector; exact local name/ID within content.definitions or retired_definitions.
    # Return this snapshot's Concept, including direct child getters; never resolve replacements.
    # Missing -> DefinitionNotFoundError; wrong kind -> DefinitionKindMismatchError.
    # No revision argument, dependency/name-alias search, live state, I/O, audit or new wire fields.
    # Removed entries remain inspectable; JSON Schema roots resolve only to active definitions.

    def serialize(self) -> bytes: ...
    @classmethod
    def deserialize(
        cls,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> DomainModelBundle: ...
    @classmethod
    def get_json_schema(cls, *, schema_version: str = "1.0") -> str: ...

    # Public value-method contract; codec implementation remains at the SDK boundary.
    # Fixed complete JSON format; serialize returns canonical UTF-8 bytes without modifying the bundle.
    # deserialize validates wire structure, hashes, closure and approval bindings; preserves all IDs.
    # InvalidBundleError / UnsupportedBundleVersionError; expected_hash checks transport bytes.
    # No Client, actor, audit, configuration, optional-adapter startup or file/network/database/inference I/O.
    # get_json_schema returns complete bundle JSON Schema text via the built-in codec schema operation.
    # Default is the current supported bundle format (1.0); schema_version selects an exact registered format.
    # UnsupportedBundleVersionError for unregistered formats; no fallback, fetching or schema migration.
    # No bundle instance required. Pass a loaded bundle's schema_version explicitly to select its format.
    # The selector is not a model release version or JSON Schema dialect; business-data projections are separate.
    # No wire/semantic mapping changes or standalone schema alias; domain records remain stdlib-only.

    def assess_projection(self, *, request: ProjectionRequest) -> ProjectionAssessment: ...

    # Public value-method contract; SDK-boundary dispatch uses the existing target mapping ports.
    # Projection types are type-only imports here; domain records do not import adapters/services.
    # Invalid bundles/requests raise existing typed errors. Missing adapters/unknown mappings and
    # analysis failures return availability/issues; unsupported content returns complete findings.
    # Optional imports remain lazy; no Client, actor, audit, network, storage, mutation, inference
    # or adapter installation. Return one immutable assessment; add no bundle wire fields.
    # Export reruns the same analysis and copies exact obligations; assessment never grants approval.

    @classmethod
    def from_approved(
        cls,
        *,
        publication: Publication,
        approval: Approval,
        bundle_id: BundleId,
        version: str,
        now: datetime,
    ) -> DomainModelBundle: ...


@dataclass(frozen=True, kw_only=True)
class BundleValidation:
    valid: bool
    schema_version: str
    issues: Sequence[Issue]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Wire structure, content hashes, internal scope/IDs and approval/snapshot bindings only.
    # Verify acceptance result coverage/binding/outcome-readiness consistency, not predicate truth.
    # Does not fetch evidence, authenticate actors or re-run optional semantic validators.
```

```python
# src/domain_kernel/modeling/domain/validation.py
from __future__ import annotations

from domain_kernel._shared.domain.acceptance import AcceptanceCheckResult

from domain_kernel._shared.domain.contracts import Issue
from domain_kernel.modeling.domain.models import (
    Candidate,
    PublicationRules,
    Readiness,
    ValidationReport,
)
from domain_kernel.modeling.domain.reference_packs import ReferencePack
from domain_kernel.review.domain.models import ReviewSnapshot


class ModelAcceptanceEvaluator:
    def evaluate(self, *, candidate: Candidate) -> tuple[AcceptanceCheckResult, ...]: ...

    # Pure built-in predicate evaluation, no I/O/reasoner or operational records.
    # Bound to candidate hash; exact evaluator-version fingerprint; UNKNOWN for ManualCriterion.


class ModelReadinessEvaluator:
    def evaluate(
        self,
        *,
        candidate: Candidate,
        validation: ValidationReport,
        reference_pack: ReferencePack | None,
        review: ReviewSnapshot,
        rules: PublicationRules,
    ) -> Readiness: ...

    # Pure domain policy; structurally satisfies the application ReadinessEvaluator port.
    # Verify captured scope/candidate/hash/pack/review bindings before evaluating required gaps.
    # Every required gap blocks; only explicitly reviewed optional questions can remain visible.
    # Structural closure, evidence sufficiency and attributed confirmation are separate checks.
    # No database, application-service/port imports, adapter execution, clock reads or writes.


class ModelInvariantValidator:
    def validate(
        self, *, candidate: Candidate, reference_pack: ReferencePack | None
    ) -> tuple[Issue, ...]: ...

    # Core IDs/revisions/meanings/evidence always checked; reference checks only when pack is present.
    # No pack: reject active reference alignments/dispositions; never fabricate a local pack.
    # Bare references resolve locally; qualified references resolve against exact dependency bundles.
    # Reject stale alignments, active references to retired definitions and unresolved re-review.
    # Retirement replacements active at decision time; historical lineage may name later tombstones.
    # Replacement lineage remains closed, acyclic and non-self-referential; no implicit redirects.
    # Dependencies: complete verified closure, same project, no conflicting pins/cycles, depth <=16.
    # Verify ontology closure hashes/headers/terms and formal link endpoint kinds/pins.
    # OWL import/subclass cycles are not model-dependency cycles; preserve them for semantic adapters.
    # Referenced external terms require a materialized closure; semantic adoption differs from provenance.
    # Unsupported source semantics get Issue codes/paths, never silently validated as supported.
    # Excluded items cannot satisfy required references, meanings or reference_pack coverage.
    # Shape type-target kinds, cardinalities/nullability, value sets, keys and embedding DAG.
    # Unit definitions require their owning name/display_name/meaning; supplied symbols are nonblank.
    # Member.unit edges resolve to active UnitDefinition bodies with inspected/exact dependency guards.
    # Reject unit plus inline ontology_term; both absent is valid for local inline codes.
    # Optional quantity_kind=None keeps QuantityBinding valid; validate supplied ontology terms only.
    # Quantity field/term bindings are structural only; dimensional validity needs an optional validator.
    # Acceptance checks: PASS only satisfies REQUIRED; preserve advisory FAIL/UNKNOWN/UNSUPPORTED/ERROR.
    # Process starts/ends/reachability, roles, inputs/outputs, activity decisions, flow endpoints.
    # Exclusive branches have conditions/default; parallel paths/joins and exception paths valid.
    # Decision inputs/outputs/types, rule conditions, hit-policy structure and required coverage.
    # Text conditions are descriptive: check references/confirmation, never claim formal proof.
    # Logical completeness/overlap only with supported formal validators; core constraints apply without a pack.
    # Required reference/definition/confirmation obligations cannot become nonblocking questions.
    # Supported descriptive BPMN/DMN subset only; no execution or full round-trip conformance.
```

```python
# src/domain_kernel/modeling/domain/interchange.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.contracts import CompanyDefinitionReference, ConsumerObligation

from domain_kernel._shared.domain.ontology_assets import OntologyClosure, OntologyClosurePin
from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    Definition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
)
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Literal
from domain_kernel._shared.domain.authoring import ModelChangePlan
from domain_kernel._shared.domain.contracts import (
    CandidatePin,
    Issue,
    ModelVersion,
    PinnedDefinitionReference,
    SchemaOrigin,
)
from domain_kernel._shared.domain.enums import LinkmlSyntax, RdfSyntax, SemanticGraphRole
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel._shared.domain.model_values import BusinessCode, MeaningText, Terminology
from domain_kernel._shared.domain.ontology import Iri, OntologyStatement


@dataclass(frozen=True, kw_only=True)
class MappingDescriptor:
    id: MappingId  # Registered mapping/version identifier.
    vocabulary_iri: Iri
    supported_capabilities: Sequence[str]
    adapter_versions: Sequence[tuple[str, str]]  # Library name/version used, stable sorted pairs.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class IdentityBinding:
    definition: PinnedDefinitionReference
    term_iri: Iri
    local_path: Sequence[str] = ()  # Empty for definition; e.g. ("attributes", attribute_id).

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


@dataclass(frozen=True, kw_only=True)
class SemanticDocument:
    model: ModelVersion
    role: SemanticGraphRole
    graph_iri: Iri
    syntax: RdfSyntax
    payload: bytes
    content_hash: ContentHash  # Exact output bytes, not an RDF graph-isomorphism claim.


@dataclass(frozen=True, kw_only=True)
class SemanticOntologyDependency:
    model: ModelVersion
    ontology: OntologyClosurePin


@dataclass(frozen=True, kw_only=True)
class SemanticProjection:
    model: ModelVersion
    base_iri: Iri
    mapping: MappingDescriptor
    documents: Sequence[SemanticDocument]  # Four roles per selected model/dependency snapshot.
    identities: Sequence[IdentityBinding]
    dependencies: Sequence[ModelVersion]  # Exact materialized closure; no implicit fetches.
    issues: Sequence[Issue]
    limitations: Sequence[str]  # Descriptive processes, no operational validation/execution claim.
    ontologies: Sequence[
        OntologyClosure
    ] = ()  # External resources, distinct from generated graph roles.
    consumer_obligations: Sequence[ConsumerObligation] = ()
    ontology_dependencies: Sequence[SemanticOntologyDependency] = ()  # Formal adoption per model.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # No partial result for unsupported required meanings. Complete SDK round-trip uses the bundle.
    # ONTOLOGY describes definitions/classes, not extracted assets or work-order records.
    # INSTANCE_SHAPES describes checks the host may run on its own separately populated graph.
    # UnitDefinition -> stable scoped dk:Unit resource, rdfs:label/comment, optional dk:symbol.
    # Metadata preserves code -> unit edges, terms/pins and quantity_kind=None without invented axioms.
    # Unit values remain string literals; closed sets still use sh:in, never implicit IRI substitution.
    # Metadata preserves required/collection/min_items/max_items separately; instance mapping is bounded.
    # SINGLE -> maxCount 1, minCount 1 only when required. SET supports optional/min=0 or required/min>0.
    # Direct predicates cannot distinguish missing from empty: other SET presence combinations are unsupported.
    # Report FIELD_PRESENCE/ITEM_BOUNDS findings and reject export; equality obligations cannot repair loss.


@dataclass(frozen=True, kw_only=True)
class ValidationGraphs:
    candidate: CandidatePin
    mapping: MappingDescriptor
    model_metadata: Sequence[OntologyStatement]
    model_shapes: Sequence[OntologyStatement]
    instance_shapes: Sequence[
        OntologyStatement
    ]  # Validate shape syntax/subset, never absent live data.
    locations: Sequence[tuple[Iri, Sequence[str | int]]]  # Nodes -> candidate diagnostic paths.
    issues: Sequence[Issue] = ()  # Typed authored-shape compilation diagnostics.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Internal deterministic validation namespace; not a published semantic artifact or approval.


@dataclass(frozen=True, kw_only=True)
class JsonSchemaProjectionRequest:
    kind: Literal["json_schema_projection"] = "json_schema_projection"
    root: (
        Definition[ConceptDefinition]
        | Definition[StructuredValueDefinition]
        | CompanyDefinitionReference
    )
    base_iri: Iri
    # Root resolves to an active concept/structured value in the exact published closure, never live state.
    # Direct objects must match a local bundle entry by scope/ID/revision and complete content.
    # Dependency roots use PinnedDefinitionReference; direct foreign objects -> ScopeMismatchError.
    # Missing/removed root -> DefinitionNotFoundError; wrong kind -> DefinitionKindMismatchError.
    # Mismatched revision/content -> StaleStateError; never silently discard the supplied snapshot.
    # Shared assessment/export normalization verifies inputs, then uses the exact pinned reference.
    # Reports/manifests/journal hashes contain normalized references, not embedded definitions;
    # equivalent object/ID/pinned-reference forms retain identical canonical projection identity.
    # No request wire/mapping change; normalization adds no I/O and preserves reference-only callers.
    # Same stable absolute HTTP(S) base convention as RDF. Mapping is dk-json-schema/1.0.
    # Artifact and x-domain-kernel retain typed consumer obligations and projection identity.
    # UnitAnnotation/UnitBindingAnnotation preserve the reachable unit closure without altering code enums.
    # Quantities retain required magnitude/unit fields and optional quantity-kind metadata.


@unique
class ProjectionAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    UNSUPPORTED_MAPPING = "unsupported_mapping"
    FAILED = "failed"


@unique
class ProjectionFeature(StrEnum):
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
    NATIVE = "native"
    ANNOTATED = "annotated"
    UNSUPPORTED = "unsupported"


@unique
class ValidationResponsibility(StrEnum):
    TARGET = "target"
    HOST = "host"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


@unique
class ProjectionRemedy(StrEnum):
    ENFORCE_IN_HOST = "enforce_in_host"
    USE_COMPLETE_BUNDLE = "use_complete_bundle"
    SELECT_SUPPORTED_TARGET = "select_supported_target"
    AUTHOR_REVIEWED_DERIVATION = "author_reviewed_derivation"
    INSTALL_OPTIONAL_DEPENDENCY = "install_optional_dependency"
    SELECT_SUPPORTED_MAPPING = "select_supported_mapping"
    INSPECT_DIAGNOSTICS = "inspect_diagnostics"


@dataclass(frozen=True, kw_only=True)
class ProjectionLocation:
    definition: PinnedDefinitionReference
    member: AttributeId | KeyId | BusinessCode | None = None
    # Nominal member kind resolves within this exact owner; None denotes the definition.


@dataclass(frozen=True, kw_only=True)
class RdfProjectionRequest:
    base_iri: Iri
    syntax: RdfSyntax = RdfSyntax.TURTLE
    mapping: MappingId = MappingId(value="dk-rdf/1.0")
    kind: Literal["rdf_projection"] = "rdf_projection"
    # All four roles and exact dependency closure, matching project_semantics.
    # Reuse for Model.export; its separate role selects an artifact after complete assessment.


@dataclass(frozen=True, kw_only=True)
class LinkmlProjectionRequest:
    base_iri: Iri
    definition_ids: Sequence[DefinitionId] | None = None
    syntax: LinkmlSyntax = LinkmlSyntax.YAML
    mapping: MappingId = MappingId(value="dk-linkml/1.0")
    kind: Literal["linkml_projection"] = "linkml_projection"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # None means all active root definitions; selected reference closure remains mandatory.


type ProjectionRequest = (
    JsonSchemaProjectionRequest | RdfProjectionRequest | LinkmlProjectionRequest
)


@dataclass(frozen=True, kw_only=True)
class ProjectionFinding:
    location: ProjectionLocation
    feature: ProjectionFeature
    representation: RepresentationSupport
    validation: ValidationResponsibility
    explanation: MeaningText
    obligations: Sequence[ConsumerObligation] = ()
    next_steps: Sequence[ProjectionRemedy] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # HOST requires relevant obligations; TARGET/NOT_APPLICABLE carry none for this finding.
    # ANNOTATED preserves metadata; generic consumers need not interpret SDK annotations.
    # Unsupported semantics are blockers, not a generic obligation that excuses loss.


@dataclass(frozen=True, kw_only=True)
class ProjectionAssessment:
    model: ModelVersion
    request: ProjectionRequest
    availability: ProjectionAvailability
    mapping: MappingDescriptor | None
    findings: Sequence[ProjectionFinding]
    consumer_obligations: Sequence[ConsumerObligation]
    issues: Sequence[Issue]
    next_steps: Sequence[ProjectionRemedy]
    content_hash: ContentHash

    @property
    def exportable(self) -> bool: ...

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # AVAILABLE requires a mapping and complete analysis of selected content/closure, not necessarily compatibility.
    # exportable iff AVAILABLE with no unsupported finding or error issue.
    # HOST obligations permit serialization, but must be fulfilled to claim instance conformance.
    # Other availability states have empty findings/obligations; no partial success claim.
    # Obligations equal the deterministically ordered, deduplicated union of finding obligations.
    # Hash binds exact source/request/mapping+library versions/results, excluding this hash field.
    # Read-only advice, not approval or an export token; adapters recheck at actual export.


@dataclass(frozen=True, kw_only=True)
class UnitAnnotation:
    source: PinnedDefinitionReference
    name: str
    display_name: str
    meaning: str
    body: UnitDefinition
    aliases: Sequence[str] = ()
    terminology: Terminology = Terminology()
    version: Literal["1"] = "1"

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Schema-level dk:units / x-domain-kernel.units entry; ordinary body codec, exact source pin.
    # Includes selected standalone units as well as referenced units; source is provenance only.


@dataclass(frozen=True, kw_only=True)
class UnitBindingAnnotation:
    source: PinnedDefinitionReference  # Owning value set.
    code: BusinessCode
    unit: PinnedDefinitionReference
    version: Literal["1"] = "1"

    def __post_init__(self) -> None: ...  # Validate exact pin/code types; no lookup or I/O.

    # dk:unit_bindings / x-domain-kernel.unit_bindings entry; exact code -> unit edge.
    # Source/member/unit must agree with selected closure; conflicting/missing entries fail.


@dataclass(frozen=True, kw_only=True)
class OpenValueSetAnnotation:
    source: PinnedDefinitionReference
    body: ValueSetDefinition
    version: Literal["1"] = "1"
    # dk:open_value_set payload; body.membership must be OPEN. Reuse the ordinary wire codec.
    # Attached to a named permissive string type; its label/description supply display_name/meaning.
    # Versioned SDK metadata preserves the stable lookup name separately.
    # Source pin is provenance, not authenticated identity or authority to merge.
    # Invalid/unknown/conflicting payloads fail import; absent payload means plain string.
    # Member.unit edges require matching UnitAnnotation/UnitBindingAnnotation entries and ID remapping.
    # Original-term resources must exist in the receiving model before plan submission.


@dataclass(frozen=True, kw_only=True)
class SchemaDocument:
    schema_iri: Iri
    syntax: LinkmlSyntax
    payload: bytes
    content_hash: ContentHash  # Required exact-byte hash, verified before parsing imports.


@dataclass(frozen=True, kw_only=True)
class LinkmlProjection:
    model: ModelVersion
    mapping: MappingDescriptor
    schema: SchemaDocument
    dependencies: Sequence[SchemaDocument]
    selected: Sequence[PinnedDefinitionReference]
    excluded_definition_ids: Sequence[DefinitionId]
    identities: Sequence[IdentityBinding]  # Both inverse slots retain relationship identity.
    issues: Sequence[Issue]
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Explicit selected scope + closure. No quiet drops or flattening of unsupported constraints.


@dataclass(frozen=True, kw_only=True)
class SchemaImportResult:
    plan: ModelChangePlan | None
    mapping: MappingDescriptor
    origins: Sequence[SchemaOrigin]
    issues: Sequence[Issue]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # None if any semantic/structural mapping error; warnings never conceal omitted required meaning.
    # New IDs, HYPOTHESIS basis and schema origins; no implicit merge, pack obligation or approval.
```

```python
# src/domain_kernel/modeling/application/interchange.py
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from domain_kernel._shared.domain.ontology_assets import OntologyClosure
from domain_kernel._shared.domain.enums import LinkmlSyntax, RdfSyntax
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel._shared.domain.ontology import Iri
from domain_kernel.modeling.domain.models import Candidate, DomainModelBundle, ModelInfo
from domain_kernel.modeling.domain.reference_packs import ReferencePack
from domain_kernel.modeling.domain.interchange import (
    LinkmlProjection,
    ProjectionAssessment,
    RdfProjectionRequest,
    LinkmlProjectionRequest,
    SchemaDocument,
    SchemaImportResult,
    SemanticProjection,
    ValidationGraphs,
)


class SemanticProjector(Protocol):
    def assess(
        self, *, bundle: DomainModelBundle, request: RdfProjectionRequest
    ) -> ProjectionAssessment: ...

    # project reuses this exact analysis; blockers fail before any artifact is produced.

    def reasoning_ontology(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
        mapping_version: str,
    ) -> OntologyClosure: ...

    # Formal asserted graph plus explicitly adopted module closures and exact dependency pins.
    # Exclude SDK review metadata/SHACL shapes and provenance-only pack ontologies from logical input.
    # Preserve external IRIs; temporary local identities follow the candidate validation namespace.
    # Unknown required mapping or unsupported OWL profile prevents a successful consistency claim.

    def validation_graphs(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
        mapping_version: str,
    ) -> ValidationGraphs: ...

    # No published bundle or caller base needed. Pure candidate + materialized pins/pack inputs.
    # https://domain-kernel.invalid/validation/{percent-encoded candidate hash}/ is internal only.
    # Shared semantic rules with project(); term/shape IDs remap consistently, no network dereference.
    # Include exact dependencies and location bindings; no fake approval/version to satisfy export types.
    # Temporary model-validation representation only; no instance extraction or authoritative RDF store.

    def project(
        self,
        *,
        bundle: DomainModelBundle,
        base_iri: Iri,
        syntax: RdfSyntax,
        mapping_version: str,
    ) -> SemanticProjection: ...

    # Application-owned port; no RDFLib types. Reuse exactly this mapping in validators/exporters.
    # Check bundle integrity; emit ontology/metadata/model-shape/instance-shape roles separately.
    # Project dependency closure recursively; same mapping/base, exact pins, bounded depth.


class LinkmlMapper(Protocol):
    def assess(
        self, *, bundle: DomainModelBundle, request: LinkmlProjectionRequest
    ) -> ProjectionAssessment: ...

    # project reuses this exact analysis; blockers fail before any artifact is produced.

    def project(
        self,
        *,
        bundle: DomainModelBundle,
        base_iri: Iri,
        definition_ids: Sequence[DefinitionId] | None,
        syntax: LinkmlSyntax,
        mapping_version: str,
    ) -> LinkmlProjection: ...
    def load(
        self,
        *,
        document: SchemaDocument,
        dependencies: Sequence[SchemaDocument],
        model_info: ModelInfo,
        reason: str,
        mapping_version: str,
        max_bytes: int,
    ) -> SchemaImportResult: ...

    # Static OPEN sets map to permissive strings plus versioned dk:open_value_set annotations;
    # never a closed enum. Import validates known-code metadata/pins and rejects narrowing conflicts.
    # Missing annotations mean a string, not an inferred value set. Dynamic enums remain unsupported.
    # Unit references map permissible-value meaning to the local unit IRI; inline ontology terms retain
    # their original meaning IRIs. No reference -> no invented meaning IRI. Operational codes stay strings.
    # Schema-level dk:units/dk:unit_bindings carry UnitAnnotation/UnitBindingAnnotation, including standalone units.
    # Import allocates fresh unit IDs once, remaps every member edge, and preserves optional kind/term pins.
    # Reject unknown annotation versions, missing bindings/units, duplicate conflicts or native/metadata drift.
    # An ordinary foreign meaning IRI alone never creates a reusable unit or proves ontology membership.
    # Strict supported-subset mapping. No framework objects leave the adapter.
    # Safe bounded decoding: max_bytes covers primary + supplied/imported schemas; nesting/cycles bounded.
    # Envelope schema_iri == parsed schema id after explicit CURIE expansion; exact absolute import lookup.
    # Before SchemaView merges, reject cycles and conflicting prefixes/class/slot/type keys or element IRIs.
    # Identical declarations may deduplicate with all origins; never last-import-wins or path/suffix fallback.
    # Only pinned packaged linkml:types or exact supplied import IRIs; no file/network resource loading.
    # No generated code execution, schema DB activation or inference. Never mutate upstream schemas.
```

```python
# src/domain_kernel/interchange.py
from __future__ import annotations

from collections.abc import Sequence
from domain_kernel._shared.domain.enums import LinkmlSyntax, RdfSyntax
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel._shared.domain.ontology import Iri
from domain_kernel.modeling.domain.models import DomainModelBundle, ModelInfo
from domain_kernel.modeling.domain.interchange import (
    LinkmlProjection,
    SchemaDocument,
    SchemaImportResult,
    SemanticProjection,
)


def project_semantics(
    *,
    bundle: DomainModelBundle,
    base_iri: Iri,
    syntax: RdfSyntax = RdfSyntax.TURTLE,
    mapping_version: str = "dk-rdf/1.0",
) -> SemanticProjection: ...


def project_linkml(
    *,
    bundle: DomainModelBundle,
    base_iri: Iri,
    definition_ids: Sequence[DefinitionId] | None = None,
    syntax: LinkmlSyntax = LinkmlSyntax.YAML,
    mapping_version: str = "dk-linkml/1.0",
) -> LinkmlProjection: ...


def load_linkml(
    *,
    document: SchemaDocument,
    model_info: ModelInfo,
    reason: str,
    dependencies: Sequence[SchemaDocument] = (),
    mapping_version: str = "dk-linkml/1.0",
    max_bytes: int = 64 * 1024 * 1024,
) -> SchemaImportResult: ...


# Standalone byte/value facade; optional adapters resolve only when the relevant operation is called.
# No Client/producer DB for projection. Import uses supplied model_info, no state read or mutation.
# Import retains the target model description; schema descriptions supply definition meanings.
# base_iri is required identity intent: absolute HTTP(S), trailing /, no query/fragment.
# None definition_ids selects all active root definitions; explicit empty/unknown selections fail.
# Selected closure includes all required refs/exact dependencies; excluded IDs remain in manifest.
# Unsupported required constructs raise UnsupportedCapabilityError (export) or return issues/no plan (import).
# Malformed/hash-invalid schemas raise InvalidSchemaError; unavailable selected extras MissingDependencyError.
# Repeated import builds a fresh proposal, never a guessed match; submit the same frozen plan for retries.
```

```python
# src/domain_kernel/modeling/infrastructure/interchange.py
from __future__ import annotations

from domain_kernel.modeling.application.interchange import LinkmlMapper, SemanticProjector


class RdfLibProjector(SemanticProjector): ...


class LinkmlSchemaMapper(LinkmlMapper): ...


# Lazy optional imports only here; adapters translate RDFLib/LinkML records to SDK-owned contracts.
# RdfLibProjector implements dk-rdf/1.0; ontology graph is distinct from SDK metadata/shape graphs.
# LinkmlSchemaMapper reuses SchemaBuilder/SchemaView/generators for dk-linkml/1.0 and checks their output.
# LinkML required is independent of multivalued/minimum_cardinality/maximum_cardinality.
# SET uses multivalued=true; map min_items, omit unbounded max_items, preserve required even when min>0.
# Imports default absent required to false, never infer it from counts; unsupported scalar counts fail.
# Set obligations cover presence, conditional item bounds and equality before host normalization.
# Reject generated schemas/annotations that strengthen, weaken or conflict with these declared fields.
# Generator availability does not imply supported semantic mapping or operational enforcement.
# SHACL validation, Turtle and JSON-LD export share the same SemanticProjector mapping service.
```

```python
# src/domain_kernel/modeling/application/service.py
from __future__ import annotations

from domain_kernel._shared.domain.audit import AuditRecord

from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol, overload

from domain_kernel._shared.domain.authoring import ModelChangePlan
from domain_kernel._shared.domain.contracts import (
    Artifact,
    Evidence,
    ModelScope,
    ModelVersion,
    Page,
    SourceRevision,
)
from domain_kernel._shared.domain.definitions import (
    ChangeSet,
    Definition,
    DefinitionBody,
    Concept,
    Process,
    ConceptDefinition,
    RelationshipDefinition,
    UnitDefinition,
)
from domain_kernel._shared.domain.enums import (
    CaseKind,
    CaseStatus,
    DefinitionStatus,
    SemanticGraphRole,
    ModelKind,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel.discovery.api.discovery import DiscoveryDraft, DiscoveryResult, ProgressCallback
from domain_kernel.modeling.domain.interchange import (
    JsonSchemaProjectionRequest,
    RdfProjectionRequest,
)
from domain_kernel.modeling.domain.models import (
    Candidate,
    DomainModelBundle,
    ModelInfo,
    Publication,
    ValidationReport,
)
from domain_kernel.modeling.domain.reference_packs import DefinitionBinding, Pattern, ReferencePack
from domain_kernel.reconciliation.api.reconciliation import Alignment
from domain_kernel.review.api.review import (
    CaseDecision,
    DecisionRecord,
    ReviewCase,
    ReviewDecision,
    ReviewImpact,
    ReviewReceipt,
)


class ReferencePacks(Protocol):
    async def get(self, *, key: str, version: str) -> ReferencePack: ...
    async def list(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ReferencePack]: ...

    # ReferencePacks are separately versioned data; the SDK embeds no industry advice.
    # Approved configured reader only; verify hashes/dependencies/license/applicability.
    # Without a catalog, list returns an empty page; get raises ReferencePackNotFoundError.
    # Unknown reference_pack/dependency fails. No remote IRI dereferencing or public download fallback.


class Definitions(Protocol):
    # Reject str/bytes/bytearray as sequence containers; validate elements, then copy to immutable tuples.
    async def get(
        self,
        *,
        name: str | None = None,
        definition_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition: ...
    async def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Concept: ...
    async def get_relationship(
        self,
        *,
        name: str | None = None,
        relationship_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[RelationshipDefinition]: ...
    async def get_process(
        self,
        *,
        name: str | None = None,
        process_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Process: ...
    async def get_unit(
        self,
        *,
        name: str | None = None,
        unit_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[UnitDefinition]: ...

    # Exactly one name/ID selector; name is exact and model-local, never an alias/display label.
    # Explicit revision selects history; otherwise return current content, including removed definitions.
    # No dependency search. Missing -> DefinitionNotFoundError; wrong kind -> DefinitionKindMismatchError.
    # Concept/Process snapshots expose direct child reads; generic definition lookup stays kind-neutral.

    async def list(
        self,
        *,
        status: DefinitionStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Definition]: ...
    async def history(
        self, *, definition_id: DefinitionId, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[Definition]: ...
    async def propose(
        self,
        *,
        actor: str,
        display_name: str | None = None,
        name: str | None = None,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_revision(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        display_name: str,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # Creation uses the definition naming contract; revisions preserve the reserved name and ID.
    # Full replacement content of the same active identity; immutable before/after snapshots.
    # Supplied evidence/aliases replace current values; history preserves earlier values.
    # Check expected_revision at creation and when applying a change; Reject can cancel stale work.
    # No active mutation until accepted.
    async def propose_retirement(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        replacement_ids: Sequence[DefinitionId] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # Accept appends a retired revision; keeps historical meaning and optional replacement lineage.
    # Replacements must be active local definitions at decision time; no self-reference/cycles.
    # Broken active references and invalidated decisions require repair/re-review before publishing.
    # Merge/split recovery composes proposals, targeted corrections, revisions and retirement.
    async def propose_restoration(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # Requires current retired revision; proposes its last content under the same ID.
    # Accept appends approved revision and clears active replacement_ids; retirement history stays.
    # Revalidate references/obligations; do not automatically restore prior mappings/confirmations.
    # Apply further content edits through propose_revision after restoration.
    async def propose_pattern(
        self,
        *,
        actor: str,
        pattern: Pattern,
        bindings: Sequence[DefinitionBinding] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...

    # Requires a selected pack; otherwise MissingCapabilityError. No pattern fallback/download.
    # Require pattern.reference_pack to match the selected pack's exact key/version/content hash.
    # Missing/foreign pin -> ScopeMismatchError; modified/unknown content -> InvalidReferencePackError.
    # Reload by ID from that pin and compare full content, including names; never substitute latest.
    # Mint independent local IDs and remap references atomically, without an adoption namespace.
    # Apply the ordinary model-local naming rules; collisions -> DefinitionAlreadyExistsError.
    # No automatic prefixes/suffixes/merges; reuse an existing definition only via explicit bindings.
    # Verify all bindings against this scope/revision; preserve upstream provenance.
    # Persist the pack pin/pattern ID and exact content in proposal provenance and request identity.
    # Return an explicit graph proposal; no automatic approval or business-choice selection.
    # No direct mutation/upstream edit; changes enter the same review path as discovery.


class ModelVersions(Protocol):
    async def get(self, *, version: str) -> DomainModelBundle: ...
    async def list(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[DomainModelBundle]: ...


class Publications(Protocol):
    async def get(self, *, publication_id: PublicationId) -> Publication: ...
    async def list(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[Publication]: ...


class Model(Protocol):
    async def get_audit_history(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[AuditRecord]: ...  # Shared audit query bound to this exact project/model.
    @property
    def info(self) -> ModelInfo: ...  # Loaded snapshot; no query or implicit freshness guarantee.
    @property
    def scope(self) -> ModelScope: ...

    # Delegates to the internal Definitions service; preserves its scope and behavior.
    async def get_definition(
        self,
        *,
        name: str | None = None,
        definition_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition: ...
    async def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Concept: ...
    async def get_relationship(
        self,
        *,
        name: str | None = None,
        relationship_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[RelationshipDefinition]: ...
    async def get_process(
        self,
        *,
        name: str | None = None,
        process_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Process: ...
    async def get_unit(
        self,
        *,
        name: str | None = None,
        unit_id: DefinitionId | None = None,
        revision: int | None = None,
    ) -> Definition[UnitDefinition]: ...

    # Exactly one name/ID selector; name is exact and model-local, never an alias/display label.
    # Explicit revision selects history; otherwise return current content, including removed definitions.
    # No dependency search. Missing -> DefinitionNotFoundError; wrong kind -> DefinitionKindMismatchError.
    # Concept/Process snapshots expose direct child reads; generic definition lookup stays kind-neutral.

    async def list_definitions(
        self,
        *,
        status: DefinitionStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[Definition]: ...
    async def get_definition_history(
        self, *, definition_id: DefinitionId, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[Definition]: ...
    async def propose_definition(
        self,
        *,
        actor: str,
        display_name: str | None = None,
        name: str | None = None,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_definition_revision(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        display_name: str,
        meaning: str,
        body: DefinitionBody,
        aliases: Sequence[str] = (),
        terminology: Terminology | None = None,
        evidence: Sequence[Evidence] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_definition_retirement(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        replacement_ids: Sequence[DefinitionId] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_definition_restoration(
        self,
        *,
        actor: str,
        definition_id: DefinitionId,
        expected_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_pattern(
        self,
        *,
        actor: str,
        pattern: Pattern,
        bindings: Sequence[DefinitionBinding] = (),
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...

    # Delegates to the internal Review service; preserves its scope and behavior.
    async def list_review_cases(
        self,
        *,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
        kind: CaseKind | None = None,
        status: CaseStatus | None = None,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[ReviewCase]: ...
    def iter_review_cases(
        self,
        *,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
        kind: CaseKind | None = None,
        status: CaseStatus | None = None,
        page_size: int = 50,
        cursor: PageCursor | None = None,
    ) -> AsyncIterator[ReviewCase]: ...
    # Lazy factory; await list_review_cases during iteration with unchanged filters and cursor semantics.
    # Same page-size limits; one materialized page at a time, no prefetch or transaction across yields.
    # Propagate errors/cancellation; early exit requests no further pages. Never decide automatically.
    # No stronger snapshot promise than pagination; use list_review_cases for explicit checkpointed pages.
    async def get_review_case(self, *, case_id: ReviewCaseId) -> ReviewCase: ...
    async def propose_confirmation(
        self,
        *,
        actor: str,
        subject: ReviewCase,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def propose_change_plan(
        self, *, actor: str, plan: ModelChangePlan, idempotency_key: str | None = None
    ) -> ReviewCase: ...
    async def propose_change_set(
        self,
        *,
        actor: str,
        decisions: Sequence[CaseDecision],
        expected_workspace_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def reopen_review_case(
        self,
        *,
        actor: str,
        case_id: ReviewCaseId,
        expected_version: int,
        reason: str,
        proposal_ids: Sequence[ProposalId] | None = None,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    async def preview_changes(
        self, *, case: ReviewCase, decision: ReviewDecision
    ) -> ReviewImpact: ...
    async def decide_review(
        self,
        *,
        case: ReviewCase,
        decision: ReviewDecision,
        actor: str,
        idempotency_key: str | None = None,
    ) -> ReviewReceipt: ...
    # Same inspected-case validation/replay rules as Review.preview/decide; actor remains host-verified.
    async def get_review_history(
        self, *, case_id: ReviewCaseId, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[DecisionRecord]: ...

    # Delegates to the internal Discovery service; preserves its scope and behavior.
    async def get_discovery_run(self, *, run_id: DiscoveryRunId) -> DiscoveryResult: ...
    async def list_discovery_runs(
        self,
        *,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[DiscoveryResult]: ...
    async def extract_proposals(
        self,
        *,
        actor: str,
        source_revisions: Sequence[SourceRevision],
        additional_instructions: str | None = None,
        prompt_override: str | None = None,
        idempotency_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DiscoveryDraft: ...
    async def resume_discovery(
        self,
        *,
        actor: str,
        run_id: DiscoveryRunId,
        idempotency_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DiscoveryResult: ...

    # Delegates to the internal Reconciliation service; preserves its scope and behavior.
    async def propose_alignment(
        self,
        *,
        actor: str,
        discovery_id: DiscoveryDraftId,
        idempotency_key: str | None = None,
    ) -> Alignment: ...
    async def get_alignment(self, *, alignment_id: AlignmentId) -> Alignment: ...

    # Delegates to the internal ModelVersions service; preserves its scope and behavior.
    async def get_version(self, *, version: str) -> DomainModelBundle: ...
    async def list_versions(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[DomainModelBundle]: ...

    # Delegates to the internal Publications service; preserves its scope and behavior.
    async def get_publication(self, *, publication_id: PublicationId) -> Publication: ...
    async def list_publications(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[Publication]: ...
    async def discover(
        self,
        *,
        actor: str,
        sources: Sequence[SourceRevision],
        additional_instructions: str | None = None,
        prompt_override: str | None = None,
        idempotency_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DiscoveryResult: ...
    # None generates a fresh discovery invocation; identical evidence is not an implicit retry key.
    # A retained caller key replays the persisted outcome; known run IDs support retrieval/resumption.
    # Both instruction arguments participate in request identity; resume reuses the captured prompt.
    # Named ingestion is explicit; verify stored project/source/revision identity before retrieval.
    # Never create sources or infer names from descriptors/paths during discovery.
    async def propose_reference_pack_change(
        self,
        *,
        actor: str,
        reference_pack: ReferencePack | None,  # Required intent: None explicitly removes the pack.
        expected_workspace_revision: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ReviewCase: ...
    # Available on unpublished/blocked workspaces; exact validated target is materialized in case.
    # Same pin or None->None is an invalid no-op; only one pending pack-change proposal per model.
    # Removal clears current reference alignments/dispositions; historical packs remain in audit.
    # Store guard at post-creation workspace revision; later workspace changes make Accept stale.
    # Accept rechecks required target capabilities and preserves local IDs/meaning/published versions.
    # Append revisions clearing old-pack alignments; audit old/new packs and full applied effects.
    # Revalidate source mappings/confirmations, create new reference review, invalidate preparations.
    # Old readiness blockers do not prevent switching; new pack/core gaps still block publication.
    # Reject cancels without changing current pack even if guard stale; host authorizes scope changes.
    # Reject proposal if any group reservation is pending; callers release those groups first.
    # Supersede only pending/deferred generated old-pack cases and unresolved questions.
    # Preserve resolved/reviewed history; deactivate its old requirements/optional exceptions.
    # Preserve core/evidence/manual work; count only current-pack obligations for readiness.
    async def prepare_publication(
        self, *, actor: str, idempotency_key: str | None = None
    ) -> Publication: ...
    # Capture, compile, validate, assess all applicable checks and CAS-persist the exact snapshot.
    # Commit Publication + idempotency outcome before returning or raising PublicationBlockedError.
    # Return only a ready snapshot; blocked results raise with error.publication (full diagnostics).
    # Replay the stored outcome: return original ready snapshot or raise with original blocked one.
    # Replay never substitutes current state; after resolving blockers, omit the key or supply a new one.
    # Failures before snapshot creation retain their own typed errors; no fabricated Publication.
    # Retrieval can return blocked snapshots; publication.ready/checks/blockers are stored views.
    # Publication still rechecks current state, scope and fingerprints atomically.
    # Granular operations remain model-bound; prepare_publication uses these.
    async def compile(self, *, actor: str) -> Candidate: ...
    # Capture reviewed model content; pending proposals are not applied by compilation.
    # Compile again after review decisions to compare their accepted effects with a publication.
    async def get_candidate(self, *, candidate_id: CandidateId) -> Candidate: ...
    async def validate(self, *, actor: str, candidate: Candidate) -> ValidationReport: ...
    async def diff(
        self,
        *,
        before: DomainModelBundle | ModelVersion | Candidate,
        after: DomainModelBundle | ModelVersion | Candidate,
    ) -> ChangeSet: ...
    # Async read-only lookup/comparison; no audit writes, import, implicit compile or latest substitution.
    # Reload exact stored snapshots for every form; verify supplied objects' scope/identity/hashes/full content.
    # Deserialized bundles must match registered publications; this is not a detached comparison helper.
    # InvalidBundleError for malformed bundle integrity; PublicationNotFoundError for absent publications;
    # StaleStateError for supplied snapshots differing from stored content; scope violations stay ScopeMismatchError.
    # Normalize valid bundles to ModelVersion; mixed forms are supported by the same comparison engine.
    # Equivalent bundle/reference inputs yield identical ChangeSet pins/content; wire records stay unchanged.
    # after must belong to this model. before is same scope OR after's exact direct baseline pin.
    # A cross-model before must be that published bundle/version, never another model's Candidate.
    # Other cross-model comparisons fail; baseline correspondence uses lineage, never labels.
    # Compare definitions/retirements, source/reference dispositions, reference_packs and dependency pins.
    # Diff never approves pending work or establishes readiness; inspect run failures and review cases separately.
    # prepare_publication compares latest version, else direct baseline, else initial empty model.
    async def publish(
        self,
        *,
        publication: Publication,
        version: str,
        actor: str,
        reason: str,
        idempotency_key: str | None = None,
    ) -> DomainModelBundle: ...
    # Reload and verify the exact stored snapshot; reject blockers, stale/forged state and scope mismatch.
    # Commit generated Approval + immutable bundle + audit + idempotency outcome in one transaction.
    # Failure creates no approval/version. Matching replay returns the same bundle before stale checks.
    # Canonical request includes publication identity/content, version, actor and reason.
    @overload
    async def export(
        self,
        *,
        actor: str,
        bundle: DomainModelBundle,
        store: str,
        path: str,
        request: None = None,
        idempotency_key: str | None = None,
    ) -> Artifact: ...
    @overload
    async def export(
        self,
        *,
        actor: str,
        bundle: DomainModelBundle,
        store: str,
        path: str,
        request: JsonSchemaProjectionRequest,
        idempotency_key: str | None = None,
    ) -> Artifact: ...
    @overload
    async def export(
        self,
        *,
        actor: str,
        bundle: DomainModelBundle,
        store: str,
        path: str,
        request: RdfProjectionRequest,
        role: SemanticGraphRole = SemanticGraphRole.ONTOLOGY,
        idempotency_key: str | None = None,
    ) -> Artifact: ...

    # Reload the exact stored bundle by scope/id; verify supplied identity/content hash and integrity.
    # Reject foreign/unregistered/forged bundles; never substitute latest publication or current draft.
    # Verify/normalize JSON Schema root snapshots with the shared assessor before journaling/rendering.
    # Equivalent object/reference roots retain canonical retry/artifact identity; invalid roots write no artifact.
    # None/omitted request -> complete canonical JSON; typed request selects projection/syntax.
    # role is RDF-only, default ONTOLOGY; select one root graph after full four-role/closure analysis.
    # LinkML retains the pure project_linkml path; it is not a stored-export request here.
    # No caller preflight required: non-exportable analysis raises ProjectionBlockedError(assessment=...)
    # before artifact I/O. Invalid input/scope and authentication/storage failures keep their own errors.
    # Export journals intent/outcome; retry with the same key verifies/reuses the exact stored request.
    # Bundle identity/hash, request, RDF role, store and path retain immutable artifact identity.
    # No overwrite, even unkeyed.
    # Canonical invocation also binds actor; identical retries verify/reuse the same artifact.
    # This artifact identity is separate from the fresh internal invocation key generated on omission.
    # Semantic export selects one root-model graph role. Full closure/manifest: project_semantics.
    # Exporters use the same registered projection mapper; no duplicated format-specific semantics.
    # Deterministic model construction, compile/validate/diff/publication need no inference gateway.
    # Required optional validators fail closed when unavailable.
    # All objects reloaded by scope/id; verify exact hashes/current workspace, review and policy.
    # reject scope mismatch/staleness; publish atomically rechecks and never overwrites.


class Models(Protocol):
    async def create(
        self,
        *,
        actor: str,
        kind: ModelKind,
        description: str,
        display_name: str | None = None,
        name: str | None = None,
        reference_pack: ReferencePack | None = None,
        copy_from: DomainModelBundle | None = None,
        dependencies: Sequence[ModelVersion] = (),
    ) -> Model: ...
    async def get(self, *, name: str) -> Model: ...
    async def list(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ModelInfo]: ...

    # Resolve/validate naming inputs before writes; require display_name or name.
    # Require a non-blank model description, including for copied models; never copy to definitions.
    # Generate name once when omitted; name-only uses that exact display label.
    # Duplicate names within this project raise ModelAlreadyExistsError, including races.
    # copy_from=None/omitted means no copy; otherwise require a DomainModelBundle, not Model/ModelVersion.
    # Reload the exact source publication in this project; verify scope, identity, hash and integrity.
    # Reject unregistered/foreign/forged bundles before creating the model; never substitute latest state.
    # Capture copy_from.model_version in baseline provenance fields; no source bundle embedded for lineage.
    # Omitted/None pack means no pack even when the source has one; no implicit inheritance.
    # Copy active definitions into fresh local IDs, remap references and retain direct source lineage.
    # Clear active old-pack reference alignments/dispositions; preserve provenance and revalidate.
    # Carry forward the source dependency pins in the same project; reject conflicting pins/closure.
    # Copies start an independent model with its own review/publication; source approvals are not inherited.
    # The source stays immutable; later source publications do not update the copy.
    # Different dependency pins require explicit model creation/review, not in-place mutation.
    # Revalidate meaning/applicability and mappings against the selected reference_pack; no inherited waiver.
    # Project is a technical namespace; no engagement/task/stakeholder lifecycle.
    # Dependency references are version-qualified; no implicit sibling/live imports.
```

```python
# src/domain_kernel/modeling/application/ports.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel._shared.domain.contracts import ConsumerObligation
from domain_kernel.modeling.domain.models import DependencyChange
from domain_kernel.modeling.domain.interchange import JsonSchemaProjectionRequest

from domain_kernel._shared.domain.enums import (
    DefinitionStatus,
    SemanticGraphRole,
)

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.domain.contracts import (
    CandidatePin,
    ModelScope,
    Page,
    ReferencePackPin,
    SemanticArtifactMetadata,
)
from domain_kernel._shared.domain.definitions import (
    ConstraintDefinition,
    Definition,
    InterpretationContext,
)
from domain_kernel.discovery.api.discovery import DiscoveryDraft
from domain_kernel.modeling.domain.models import (
    Candidate,
    DomainModelBundle,
    ModelContent,
    ModelInfo,
    Publication,
    PublicationRules,
    Readiness,
    ValidationReport,
)
from domain_kernel.modeling.domain.reference_packs import (
    ReferencePack,
    ReferencePackBuild,
    ReferencePackSpec,
    ReferencePackValidation,
)
from domain_kernel.review.api.review import ReviewSnapshot


@dataclass(frozen=True, kw_only=True)
class CompilationInput:
    context: InterpretationContext
    drafts: Sequence[DiscoveryDraft]
    review: ReviewSnapshot
    definitions: Sequence[Definition]
    baseline: DomainModelBundle | None
    dependencies: Sequence[DomainModelBundle]

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


class WorkspaceReader(Protocol):
    async def context(self, *, scope: ModelScope) -> InterpretationContext: ...


class ModelCompiler(Protocol):
    def compile(self, *, inputs: CompilationInput) -> Candidate: ...


class SemanticValidator(Protocol):
    @property
    def fingerprint(self) -> str: ...  # Immutable engine/profile/options/mapping identity.

    async def validate(
        self, *, candidate: Candidate, reference_pack: ReferencePack | None
    ) -> ValidationReport: ...


class ReadinessEvaluator(Protocol):
    # Application-owned port, fulfilled structurally by the pure domain ModelReadinessEvaluator.
    # Services provide captured inputs; the port does not move publication policy into application code.
    def evaluate(
        self,
        *,
        candidate: Candidate,
        validation: ValidationReport,
        reference_pack: ReferencePack | None,
        review: ReviewSnapshot,
        rules: PublicationRules,
    ) -> Readiness: ...


@dataclass(frozen=True, kw_only=True)
class ReferenceIdBinding:
    source_id: ReferenceDefinitionId
    target_id: ReferenceDefinitionId


class SemanticReferenceMapper(Protocol):
    def supports(
        self, *, constraint: ConstraintDefinition, semantic_mapping_version: str
    ) -> bool: ...
    def remap(
        self, *, constraint: ConstraintDefinition, bindings: Sequence[ReferenceIdBinding]
    ) -> ConstraintDefinition: ...

    # Only explicitly supported formal semantics; no string replacement in arbitrary expressions.


class ReferencePackComposer(Protocol):
    def compose(
        self, *, spec: ReferencePackSpec, actor: str, reason: str
    ) -> ReferencePackBuild: ...
    def validate(self, *, reference_pack: ReferencePack) -> ReferencePackValidation: ...

    # Pure typed inputs; namespace all imported IDs/internal refs and selected patterns/obligations.
    # All imported definitions copied; selected requiredness preserved; omitted obligations recorded.
    # Preserve source origins/licenses, scope blank nodes, never infer equivalence or fetch IRIs.
    # Duplicate namespaces/IDs/pattern names, dangling refs, conflicting dependencies/versions -> Issues.
    # Unknown required semantics or unavailable needed remapper -> composition error, no usable pack.
    # Validator installation is checked at model adoption; structural composition doesn't execute rules.


class ReferencePackCatalogReader(Protocol):
    # Reader implementation uses approved SourceReader bindings; materialize pins at creation.
    async def get(self, *, key: str, version: str) -> ReferencePack: ...
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ReferencePack]: ...


@dataclass(frozen=True, kw_only=True)
class ExportPayload:
    media_type: str
    content_hash: ContentHash
    chunks: Iterable[bytes]
    projection_limits: Sequence[str]  # Persist alongside projections; JSON bundle is complete.
    semantic: SemanticArtifactMetadata | None = None  # Copy into the stored Artifact unchanged.
    consumer_obligations: Sequence[
        ConsumerObligation
    ] = ()  # Copy into Artifact and embedded manifest.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.


from domain_kernel.modeling.domain.interchange import (
    ProjectionAssessment,
    RdfProjectionRequest,
)


class ModelExporter(Protocol):
    def assess(
        self,
        *,
        bundle: DomainModelBundle,
        request: JsonSchemaProjectionRequest | RdfProjectionRequest,
    ) -> ProjectionAssessment: ...

    # JSON Schema shares its mapping analysis with render; RDF delegates to SemanticProjector.
    # Normalize roots against the supplied bundle using JsonSchemaProjectionRequest's contract.
    # Return normalized pinned roots in assessments; do not hash or embed caller definition payloads.
    # JSON property names use stable attribute.name; IDs remain in identity metadata and manifests.
    # JSON object required derives only from attribute.required; array minItems/maxItems apply when present.
    # SINGLE emits no item bounds; LIST/SET retain independent presence and item limits.
    # LinkML uses owner-qualified stable slot names when needed; RDF term identity stays ID-based.
    # RDF render assesses full four-role projection before selecting the requested artifact role.
    # Normalize existing mapping_version strings to MappingId at the boundary; no duplicate logic.
    # render checks blockers before serialization/storage and preserves the assessed obligations.

    def render(
        self,
        *,
        bundle: DomainModelBundle,
        request: JsonSchemaProjectionRequest | RdfProjectionRequest | None = None,
        role: SemanticGraphRole | None = None,
    ) -> ExportPayload: ...

    # Typed request selects JSON Schema/RDF; None means complete JSON. No suffix inference.
    # role is RDF-only (None resolves to ONTOLOGY); reject it for JSON Schema/complete JSON.
    # Every non-exportable analysis raises ProjectionBlockedError with the exact assessment.
    # Assessment failure happens before output chunks/storage; no successful partial projection.
    # Preserve typed consumer obligations through ExportPayload -> artifact store -> Artifact.
    # JSON delegates to BundleCodec.serialize; byte identity matches bundle.serialize().
    # Projections report omissions; unsupported essential identities/required constructs raise
    # ProjectionBlockedError. No silent flattening of version-qualified identities.


class ModelRepository(Protocol):
    async def change_dependencies(
        self, *, expected: ModelInfo, change: DependencyChange
    ) -> None: ...
    # Reviewed transition transaction only: expected scope/revision/pins must match the parent guard.
    # change.request.before == expected.dependencies; verify/materialize both exact bundle closures.
    # Store after pins and historical audit resources; do not advance independently.
    # Coordinator commits pins/content/review/audit/idempotency with one workspace advance or rolls back all.
    async def create(self, *, info: ModelInfo, reference_pack: ReferencePack | None) -> None: ...
    async def get(self, *, project_id: ProjectId, name: str) -> ModelInfo: ...
    async def list(
        self, *, project_id: ProjectId, limit: int, cursor: PageCursor | None
    ) -> Page[ModelInfo]: ...
    async def context(self, *, scope: ModelScope) -> InterpretationContext: ...
    async def advance(self, *, scope: ModelScope, expected_revision: int) -> None: ...
    async def get_reference_pack(self, *, pin: ReferencePackPin) -> ReferencePack: ...
    async def change_reference_pack(
        self,
        *,
        scope: ModelScope,
        reference_pack: ReferencePack | None,
        expected_pin: ReferencePackPin | None,
        expected_revision: int,
    ) -> None: ...
    # Used only inside reviewed transition txn; stores immutable pack and updates active model pin.
    # Does not independently advance workspace; coordinator commits exactly one advance with audit.
    async def get_definition(
        self, *, scope: ModelScope, definition_id: DefinitionId, revision: int | None
    ) -> Definition: ...
    # Append-only definition revisions; upstream reference_pack records remain immutable.
    async def list_definitions(
        self,
        *,
        scope: ModelScope,
        status: DefinitionStatus | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]: ...
    async def get_definition_by_name(
        self, *, scope: ModelScope, name: str, revision: int | None = None
    ) -> Definition: ...
    # Resolve the reserved catalog name to an identity, then load its requested/current revision.
    # Unique (project_id, model_id, name) on identities/reservations, not historical revision rows.
    # Reserve names atomically for authored additions; never reuse names of removed identities.
    # Rejection of a never-approved creation releases its pending name reservation; retain ID/history.
    # Repeated discovery occurrences are proposals, not competing catalog-name reservations.
    async def definition_history(
        self,
        *,
        scope: ModelScope,
        definition_id: DefinitionId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]: ...
    async def save_definition(
        self, *, definition: Definition, expected_revision: int | None
    ) -> None: ...
    async def get_content(self, *, scope: ModelScope) -> ModelContent: ...
    async def save_content(
        self, *, scope: ModelScope, content: ModelContent, expected_revision: int
    ) -> None: ...
    async def add_candidate(self, *, candidate: Candidate) -> None: ...
    async def get_candidate(self, *, reference: CandidatePin) -> Candidate: ...
    async def find_candidate(
        self, *, scope: ModelScope, candidate_id: CandidateId
    ) -> Candidate: ...
    async def save_validation(self, *, report: ValidationReport) -> None: ...
    async def save_publication(
        self,
        *,
        publication: Publication,
        expected_workspace_revision: int,
        expected_review_version: int,
    ) -> None: ...
    async def get_publication(
        self, *, scope: ModelScope, publication_id: PublicationId
    ) -> Publication: ...
    async def list_publications(
        self, *, scope: ModelScope, limit: int, cursor: PageCursor | None
    ) -> Page[Publication]: ...
    async def get_version(self, *, scope: ModelScope, version: str) -> DomainModelBundle: ...
    async def get_published(
        self, *, scope: ModelScope, published_id: BundleId
    ) -> DomainModelBundle: ...
    async def list_versions(
        self, *, scope: ModelScope, limit: int, cursor: PageCursor | None
    ) -> Page[DomainModelBundle]: ...
    async def publish(
        self,
        *,
        bundle: DomainModelBundle,
        expected_workspace_revision: int,
        expected_review_version: int,
    ) -> None: ...

    # Create enforces unique (project_id, name) atomically; collision -> ModelAlreadyExistsError.
    # No suffix or implicit retrieval. Versions remain unique (project_id, model_id, version).
    # Preparation checks snapshots at commit; publish verifies state and stores bundle.approval atomically.
    # Store materialized reference_pack manifests, ontology dependencies and canonical content, not just pins.
    # Preparations and published bundles, including their Approval records, survive process restarts.


class ModelingTransaction(Transaction, Protocol):
    @property
    def models(self) -> ModelRepository: ...
```

```python
# src/domain_kernel/modeling/application/serialization.py
from __future__ import annotations

from domain_kernel.shared.identifiers.content_hash import ContentHash

from typing import Protocol

from domain_kernel.modeling.domain.models import BundleValidation, DomainModelBundle
from domain_kernel.modeling.domain.reference_packs import ReferencePack, ReferencePackValidation


class ReferencePackCodec(Protocol):
    def loads(
        self,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> ReferencePack: ...
    def dumps(self, *, reference_pack: ReferencePack) -> bytes: ...
    def validate(self, *, reference_pack: ReferencePack) -> ReferencePackValidation: ...
    def schema(self, *, version: str = "1.0") -> str: ...

    # Closed versioned wire form mirrors ReferencePack, format=domain-kernel.reference-pack.
    # Same scalar/bytes/closure/canonical JSON rules as bundle codec; pack hash excludes pin.content_hash only.
    # Pattern wire content includes stable ID/name/display_name; no new IDs/slugs on load.
    # Pattern.reference_pack is runtime context, not a wire field; reattach the verified containing pin.
    # The same rule applies to ReferenceDefinition.reference_pack, including definitions in patterns.
    # Composition reattaches the destination pin without changing source packs or embedding self-hashes.
    # Preserve composition selections, omissions and origins. No catalog/network/DB/inference I/O.
    # InvalidReferencePackError for malformed/hash/closure failures; UnsupportedReferencePackVersionError
    # for unregistered schema versions. Missing catalog assets use ReferencePackNotFoundError.
    # Expected_hash verifies transport bytes; max_bytes covers entire input before decoding.


class BundleCodec(Protocol):
    def deserialize(
        self,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> DomainModelBundle: ...
    def serialize(self, *, bundle: DomainModelBundle) -> bytes: ...
    def validate(self, *, bundle: DomainModelBundle) -> BundleValidation: ...
    def schema(self, *, version: str = "1.0") -> str: ...

    # format=domain-kernel.bundle, schema_version=1.0; fields match records except scalar/bytes codecs below.
    # Closed JSON Schema 2020-12: required fields, explicit nulls, arrays for tuples, kind tags.
    # Reject unknown fields/tags/versions, duplicate JSON keys, nonfinite numbers and malformed IDs.
    # Strict scalar validation; no coercion, IRI/context fetch, DB, gateway, settings or parser startup.
    # UTF-8 canonical output: keys sorted by Unicode code point, no insignificant whitespace,
    # non-ASCII characters unescaped, array order retained, integers in minimal decimal form.
    # Datetimes are UTC RFC3339 with fixed six-digit fractional seconds; dates are YYYY-MM-DD.
    # DecisionValue has native Python value + derived DataType. Wire uses {data_type, lexical_value}:
    # decimal has no exponent/trailing zeros; integer has no leading zeros; boolean=true/false.
    # Date/datetime use the canonical forms above; strings stay strings. Null outputs are unsupported.
    # Scalar mapping and bytes encoding are the exceptions to native field-value representation.
    # Zero has no negative sign; all strings must contain valid Unicode scalar values.
    # Candidate/Bundle hashes exclude their own root content_hash; ReferencePack excludes pin.content_hash.
    # Candidate.description is required, preserved and hashed as model metadata, not definition content.
    # OntologyClosure/ModelComposition/ModelSlice hashes exclude only their own root content_hash.
    # OntologyDocument.payload uses strict RFC 4648 standard padded base64, no whitespace/URL alphabet;
    # decoded byte hashes are verified and both encoded/decoded sizes bounded before allocation.
    # Closures sort/deduplicate documents/resources by canonical full pin (including graph selector),
    # bindings/terms/statements by canonical JSON record bytes. Conflicting duplicates fail.
    # Blank-node IDs remain document-scoped; never claim graph canonicalization/isomorphism hashes.
    # Compositions sort unique roots/bundles by canonical ModelVersion; slices sort refs by exact pin/ID/revision.
    # Closure digest includes parser identity, raw-byte pins, parsed records and selected graph/context bindings.
    # Structural load verifies these records/hashes without starting parsers/reasoners or claiming semantic proof.
    # Reasoning/acceptance outputs are in publication/bundle hashes, not their input candidate hash.
    # New nominal single-value objects encode as validated scalar values, not {value: ...} wrappers.
    # AttributeId/KeyId/BusinessCode/LanguageTag/text VOs are strings; Count/precision/scale are integers.
    # Attribute wire fields required/collection/min_items/max_items are all explicit and hashed.
    # SINGLE has null item bounds; SET/LIST has canonical integer min_items and integer-or-null max_items.
    # Presence never derives from bounds. Reject legacy attribute shape fields; no implicit migration.
    # Shape/predicate/consumer-obligation unions use closed kind tags; no primitive shortcuts in Python.
    # UnitDefinition uses kind=unit; symbol/ontology_term, member.unit and quantity_kind are explicit nullable fields.
    # Preserve/hash unit bodies and owning metadata, code -> unit references, and all supplied ontology pins.
    # Rehydrate stable unit IDs; validate active closure/kinds, mutually exclusive bindings and historical scope.
    # Localized metadata and business codes participate in definition/content hashes.
    # Model-owned definitions retain name/display_name; display labels never replace stable lookup names.
    # DefinitionKind enum members encode their fixed string values, not enum names or wrapper records.
    # Concept snapshots expose direct read helpers with the same Definition wire representation.
    # Materialize concept/process bodies as Concept/Process on load and reads, including generic lookups.
    # Process children preserve/hash generated nominal IDs, name/display_name and all typed stored edges.
    # Serialize IDs as strings; restore exact types (node ID kind from referenced body member), never remint.
    # Reject unknown/mistyped/dangling child IDs, duplicate names and legacy process record shapes.
    # No runtime inspected-object context or embedded definitions in process wire bodies; plan bindings persist.
    # Shared Condition/DecisionRule condition references follow the same generated ConditionId contract.
    # Copy/pattern adoption creates fresh child IDs under each new owner and remaps every local edge.
    # Preserve child names; separately remap model-definition references with the normal scope/pin rules.
    # Projections preserve supported child structure or report limits/blockers; never imply execution.
    # Extend unreleased v1 schema/mapping drafts together; released incompatible records require new versions.
    # Attribute/key records retain generated IDs, names and display names on reload; never mint replacements.
    # ReviewCase snapshots retain generated_member_case_ids; validate distinct membership and plan origin.
    # Decision snapshots preserve that provenance and released_case_ids for portable rejection audit.
    # Released and generated IDs are disjoint; child rejection records cover generated members only.
    # Persist rejection provenance and linked parent/generated decisions; releases are not child Rejects.
    # DependencyChange retains before/after bundles, verified independently under each historical closure.
    # Never merge historical pins into active dependency conflict checks; all bytes/nesting remain bounded.
    # Dependency request before/after pins and generated applied changes must agree with parent audit.
    # Acceptance results identify exact active checks through candidate_hash; one per local check required.
    # Remaining hash-bearing records are pins/digests of referenced assets, not metadata digests.
    # Decimal fields use exact canonical strings, never binary floats; no negative zero or exponent.
    # Candidate/Publication/Validation nullable pack pins must agree; present packs verify hashes.
    # No pack is explicit JSON null. Core semantic_mapping_version=1.0 exists independently.
    # With no pack, current definitions have no reference alignments and reference_dispositions=().
    # Historical audit may retain previous packs; expected_hash hashes the original input bytes.
    # Graph IDs/revisions and source-alignment proposal IDs close within materialized content.
    # Case/run IDs are opaque audit identities; baseline links are explicit provenance pins.
    # Qualified references resolve in materialized dependency_bundles, matching exact pins/revisions.
    # Validate recursive dependencies: same project, no conflicting pins/cycles, at most 16 edges.
    # max_bytes applies to the whole payload; reject excessive nesting before recursive decoding.
    # Active references cannot target tombstones. Historical decision/change payloads retain their
    # historical IDs/revisions; do not require them to be active in the current snapshot.
    # Supersession target decisions must be materialized; occurrence scopes cannot exceed targets.
    # Pin unions use disjoint required fields (version vs candidate_id); refs are string or tagged.
    # Diff before/after pins identify snapshots; they do not embed or fetch historical bundles.
    # Verify pack-change before/after hashes and parent/member audit links (same scope, acyclic).
    # Historical applied changes may name old packs/revisions; current content uses current pack.
    # Parent aggregate + member applied changes describe one atomic commit, never duplicate effects.
    # Parent change_plan preserves tagged operations, snapshot guards and typed IDs; no live builders.
    # Schema origins preserve exact input/dependency hashes and element paths; no implicit dereference.
    # Historical plan targets are audited snapshots, not required to match current active revisions.
    # dumps validates before encoding; loads validates wire, closure, digests and approval binding.
    # Published readiness is an attributed historical result, not a guarantee of business truth.
    # Version 1.0 is initially supported. Reject all unregistered versions; never migrate silently.
    # Schema breaking changes require a new major; compatible additions require a registered minor.
```

```python
# src/domain_kernel/modeling/application/compiler.py
from __future__ import annotations

from domain_kernel.modeling.application.ports import ModelCompiler


class ReviewedModelCompiler(ModelCompiler): ...


# Materialize approved definitions, separate retirement tombstones, and current alignment state.
# Semantic links/modules are ordinary reviewed bodies; preserve complete typed ontology closures.
# Source pins and formal assertions participate in candidate hashes. Reasoning reports are outputs
# bound to that candidate and hashed in the publication/bundle, never in their own input candidate.
# Include stale/unresolved dispositions for readiness diagnostics; never treat them as approvals.
# Preserve pinned baseline/dependency lineage, kind, evidence and all typed review payloads.
# Unresolved proposals/gaps become readiness blockers, never invented canonical definitions.
# Materialize proposal occurrences and relevant typed decisions, including correction predecessors.
# Include exact dependency bundles recursively; standalone consumers never need producer DB lookups.
```

```python
# src/domain_kernel/modeling/application/validation.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.application.ports import SemanticValidator
from domain_kernel.modeling.domain.validation import (
    ModelInvariantValidator,
    ModelAcceptanceEvaluator,
)


class CompositeModelValidator(SemanticValidator):
    def __init__(
        self,
        *,
        invariants: ModelInvariantValidator,
        acceptance: ModelAcceptanceEvaluator,
        semantic: Sequence[SemanticValidator] = (),
    ) -> None: ...

    # Core acceptance evaluation always runs; aggregate results once, never overwrite with adapter results.
    # Unsupported required semantics block; never silently skip reference_pack validation.


# Orchestrate validators here; readiness policy lives in modeling/domain/validation.py.
# Preparation supplies captured results to that policy, then persists through application transactions.
```

```python
# src/domain_kernel/modeling/api/modeling.py
from __future__ import annotations

from domain_kernel._shared.domain.enums import (
    ExportFormat,
    ModelKind,
)

from domain_kernel.modeling.application.service import (
    Definitions,
    Model,
    Models,
    ModelVersions,
    ReferencePacks,
    Publications,
)
from domain_kernel.modeling.domain.models import (
    Approval,
    BundleValidation,
    Candidate,
    DomainModelBundle,
    ModelInfo,
    Publication,
    Readiness,
    ValidationReport,
)
from domain_kernel.modeling.domain.reference_packs import (
    DefinitionBinding,
    Pattern,
    ReferencePack,
    ReferencePackSpec,
    ReferencePackImport,
    ReferencePackBuild,
    ReferencePackValidation,
    ReferencePackChange,
    ReferenceOrigin,
    ReferencePackDependency,
    ReferencePackObligation,
    ReferenceDefinition,
)

__all__ = [
    "Definitions",
    "ExportFormat",
    "Model",
    "Models",
    "ModelVersions",
    "ReferencePacks",
    "Publications",
    "Approval",
    "BundleValidation",
    "Candidate",
    "DomainModelBundle",
    "ModelInfo",
    "ModelKind",
    "Publication",
    "Readiness",
    "ValidationReport",
    "DefinitionBinding",
    "Pattern",
    "ReferencePack",
    "ReferencePackSpec",
    "ReferencePackImport",
    "ReferencePackBuild",
    "ReferencePackValidation",
    "ReferencePackChange",
    "ReferenceOrigin",
    "ReferencePackDependency",
    "ReferencePackObligation",
    "ReferenceDefinition",
]
```

```python
# src/domain_kernel/modeling/infrastructure/reference_packs.py
from __future__ import annotations

from domain_kernel.configuration import ReferencePackCatalog
from domain_kernel.modeling.application.ports import ReferencePackCatalogReader
from domain_kernel.modeling.application.serialization import ReferencePackCodec
from domain_kernel.sources.application.ports import SourceReader


class ApprovedReferencePackCatalog(ReferencePackCatalogReader):
    def __init__(
        self,
        *,
        configuration: ReferencePackCatalog,
        reader: SourceReader,
        codec: ReferencePackCodec,
    ) -> None: ...

    # Verify versioned manifest/content hashes/dependencies; persist exact ReferencePack on creation.
    # Reject path escape, unsupported required semantics, missing dependencies and unknown pins.
```

```python
# src/domain_kernel/modeling/application/ontology_validation.py
from __future__ import annotations

from domain_kernel.modeling.application.ports import SemanticValidator
from domain_kernel.modeling.application.interchange import SemanticProjector
from domain_kernel.modeling.application.ontology import OntologyReasoner
from domain_kernel.modeling.domain.semantics import ReasoningRequest
from domain_kernel._shared.domain.ontology_assets import OntologyLimits


class ReasoningModelValidator(SemanticValidator):
    def __init__(
        self,
        *,
        projector: SemanticProjector,
        reasoner: OntologyReasoner,
        request: ReasoningRequest,
        limits: OntologyLimits | None = None,
    ) -> None: ...

    # Required selected check; candidate-specific input and result stored in ValidationReport.reasoning.
    # Only complete requested results satisfy readiness; missing/incomplete/unknown blocks.
    # Initial candidate validator accepts only CONSISTENCY or CLASSIFICATION of all named classes.
    # Reject query/nonempty signature/ENTAILMENT at construction: local candidate IRIs do not exist yet.
    # CONSISTENCY requires consistent=True; CLASSIFICATION also rejects unsatisfiable named classes.
    # Standalone reason_ontology retains scoped/entailment tasks on known immutable ontology inputs.
```

```python
# src/domain_kernel/modeling/infrastructure/validation.py
from __future__ import annotations

from domain_kernel.modeling.application.ports import SemanticValidator


from domain_kernel.modeling.application.interchange import SemanticProjector


class ShaclModelValidator(SemanticValidator):
    def __init__(self, *, projector: SemanticProjector | None = None) -> None: ...
    @property
    def core_predicates(self) -> tuple[Iri, ...]: ...
    @property
    def extensions(self) -> tuple[Iri, ...]: ...
    @property
    def entailment(self) -> str: ...

    # Optional ontology extra; obtains ValidationGraphs directly from the candidate and selected pack.


# Use the shared dk-rdf mapper: MODEL constraints target model metadata, never empty instance data.
# INSTANCE constraints are syntax/subset/closure checked and exported; no claim to validate live records.
# No remote imports, SHACL-JS or uncontrolled executable/SPARQL extensions.
```

```python
# src/domain_kernel/modeling/infrastructure/exporters.py
from __future__ import annotations

from domain_kernel.modeling.application.ports import ModelExporter


class JsonBundleExporter(ModelExporter): ...


class JsonSchemaExporter(ModelExporter): ...


class JsonLdExporter(ModelExporter): ...


class TurtleExporter(ModelExporter): ...
```

```python
# src/domain_kernel/modeling/infrastructure/serialization.py
from __future__ import annotations

from domain_kernel.modeling.application.serialization import BundleCodec, ReferencePackCodec


class PydanticReferencePackCodec(ReferencePackCodec):
    def __init__(self) -> None: ...


class PydanticBundleCodec(BundleCodec):
    def __init__(self) -> None: ...

    # Versioned strict wire schemas and explicit domain mappers live here; no framework in domain.
    # Preserve stable IDs, exact decimal lexical values, reference_pack materialization and full provenance.
    # Built-in structural codec imports no optional adapters and initializes no configuration.
```

```python
# src/domain_kernel/project.py
from __future__ import annotations

from domain_kernel._shared.domain.audit import AuditRecord

from collections.abc import Sequence
from typing import Protocol

from domain_kernel._shared.domain.contracts import (
    Evidence,
    ModelVersion,
    Page,
    ProjectInfo,
    SourceRevision,
)
from domain_kernel._shared.domain.enums import ModelKind
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.modeling.api.modeling import Model
from domain_kernel.modeling.domain.models import DomainModelBundle, ModelInfo
from domain_kernel.modeling.domain.reference_packs import ReferencePack
from domain_kernel.sources.api.sources import (
    CopyTo,
    EvidenceContent,
    IngestedSource,
    OriginalCopy,
    Source,
    SourceDescriptor,
    SourceInput,
    SourceFolder,
    BatchIngestionResult,
    SourceProfile,
)


class Project(Protocol):
    async def get_audit_history(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[AuditRecord]: ...  # Shared audit query for this project, including all its models.
    @property
    def id(self) -> ProjectId: ...
    @property
    def name(self) -> str: ...
    @property
    def display_name(self) -> str: ...

    # Delegates to the internal Models service; preserves its scope and behavior.
    async def create_model(
        self,
        *,
        actor: str,
        kind: ModelKind,
        description: str,
        display_name: str | None = None,
        name: str | None = None,
        reference_pack: ReferencePack | None = None,
        copy_from: DomainModelBundle | None = None,
        dependencies: Sequence[ModelVersion] = (),
    ) -> Model: ...
    async def get_model(self, *, name: str) -> Model: ...
    async def list_models(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ModelInfo]: ...

    # Delegates to the internal Sources service; preserves its scope and behavior.
    async def ingest_source(
        self,
        *,
        actor: str,
        source: SourceDescriptor,
        display_name: str | None = None,
        name: str | None = None,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource: ...
    async def ingest_sources(
        self,
        *,
        actor: str,
        sources: Sequence[SourceInput | SourceFolder],
        max_concurrent_sources: int | None = None,
        max_files: int | None = None,
    ) -> BatchIngestionResult: ...
    async def ingest_source_revision(
        self,
        *,
        actor: str,
        source_id: SourceId,
        source: SourceDescriptor,
        retain_original: CopyTo | None = None,
        idempotency_key: str | None = None,
    ) -> IngestedSource: ...
    async def get_source(
        self, *, name: str | None = None, source_id: SourceId | None = None
    ) -> Source: ...
    async def list_sources(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[Source]: ...
    async def profile_source(self, *, actor: str, revision: SourceRevision) -> SourceProfile: ...
    async def copy_source_original(
        self,
        *,
        actor: str,
        revision: SourceRevision,
        destination: CopyTo,
        idempotency_key: str | None = None,
    ) -> OriginalCopy: ...

    # Delegates to the internal SourceRevisions service; preserves its scope and behavior.
    async def get_source_revision(
        self, *, source_id: SourceId, revision_id: SourceRevisionId
    ) -> SourceRevision: ...
    async def list_source_revisions(
        self,
        *,
        source_id: SourceId,
        limit: int = 50,
        cursor: PageCursor | None = None,
    ) -> Page[SourceRevision]: ...

    # Accept an existing citation, e.g. one selected from IngestedSource.evidence when nonempty.
    # Return EvidenceContent with excerpt, citation and verified origin; retrieval may perform I/O.
    # Delegates to the internal EvidenceAccess service; preserves its scope and behavior.
    async def get_evidence(self, *, evidence: Evidence) -> EvidenceContent: ...


class Projects(Protocol):
    # Same naming rules as Models; catalog-wide uniqueness, ProjectAlreadyExistsError on collision.
    async def create(
        self, *, actor: str, display_name: str | None = None, name: str | None = None
    ) -> Project: ...
    async def get(self, *, name: str) -> Project: ...
    async def list(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ProjectInfo]: ...
```

```python
# src/domain_kernel/_composition.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.application.ports import SemanticValidator

from domain_kernel.shared.identifiers.page_cursor import PageCursor

from dataclasses import dataclass
from typing import Protocol

from domain_kernel._settings import RuntimeSettings
from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel._shared.application.storage import ArtifactStore
from domain_kernel._shared.domain.contracts import Page, ProjectInfo
from domain_kernel.configuration import ReaderConfiguration, StoreConfiguration
from domain_kernel.discovery.application.ports import DiscoveryTransaction
from domain_kernel.modeling.api.modeling import ReferencePacks
from domain_kernel.modeling.application.ports import ModelingTransaction
from domain_kernel.project import Projects
from domain_kernel.reconciliation.application.ports import ReconciliationTransaction
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.sources.application.ports import (
    ParsedSourceResolver,
    SourceReader,
    SourcesTransaction,
)

# SDK composition boundary; project catalog metadata does not add another domain slice.


class ProjectCatalog(Protocol):
    # Enforce unique name atomically; collision -> ProjectAlreadyExistsError, never suffix/retrieve.
    async def create(self, *, project: ProjectInfo) -> None: ...
    async def get(self, *, name: str) -> ProjectInfo: ...
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]: ...


class KernelTransaction(
    SourcesTransaction,
    DiscoveryTransaction,
    ReconciliationTransaction,
    ReviewTransaction,
    ModelingTransaction,
    Protocol,
):
    @property
    def projects(self) -> ProjectCatalog: ...


@dataclass(frozen=True, kw_only=True)
class ReaderBinding:
    configuration: ReaderConfiguration
    adapter: SourceReader


@dataclass(frozen=True, kw_only=True)
class StoreBinding:
    configuration: StoreConfiguration
    adapter: ArtifactStore


@dataclass(frozen=True, kw_only=True)
class ClientIntegrations:
    # Ready adapters may wrap caller-owned transports/pools; SDK never closes those owners.
    readers: Sequence[ReaderBinding] = ()
    parsed_source_providers: Sequence[ParsedSourceProvider] = ()
    stores: Sequence[StoreBinding] = ()
    transactions: UnitOfWorkFactory[KernelTransaction] | None = None
    validators: Sequence[
        SemanticValidator
    ] = ()  # Additional required configured checks, never replace core.

    def __post_init__(self) -> None: ...  # Validate and freeze sequence fields.

    # Parsed-source provider names are unique/non-blank; ParsedSourceOrigin.provider selects a provider by name.
    # Validate/snapshot integrations at client startup, retaining exact caller-owned resolver references.
    # Registration performs no retrieval; the existing client/project/model handles reuse these integrations.


@dataclass(frozen=True, kw_only=True)
class Services:
    projects: Projects
    reference_packs: ReferencePacks


def build_services(
    *,
    settings: RuntimeSettings,
    integrations: ClientIntegrations | None = None,
) -> Services: ...  # Bind typed ports; no schema provisioning or project creation.


# Long-lived Services hold factories, not live sessions or session-bound use-case instances.
# For each operation, enter UnitOfWorkFactory and inject individual collaborators from
# KernelTransaction into a fresh service. Inject the bundle as TransactionManager only
# for begin(); business services never access its repository properties.
# Resource entry/exit acquires/releases the session; begin() alone commits/rolls back.
# Every durable action uses the same session for state, audit, revisions and outcomes.
# Coordinators capture actor/parent context and append typed records with each committed effect.
# Pure builders/readers/projections have no audit writes; reads never initiate derivative retention.
# External copy/export journals intent before I/O, verifies bytes, then commits outcome/audit;
# recovery completes the same intent without duplicate success, never a claimed cross-store transaction.
# KernelTransaction is the coordinator boundary for cross-slice use cases:
# discovery: lease/checkpoint/draft/outcome, then release before parsing/inference;
# reconciliation: grouped cases + alignment checkpoint + workspace revision + outcome;
# review: case CAS + typed audit + definitions/dispositions + workspace revision + outcome;
# prepare_publication: capture workspace/review pins, compute outside txn, CAS-persist exact
# Publication + outcome, commit, then return if ready or raise PublicationBlockedError with it;
# publish: reload exact preparation; scope/hash/state/policy CAS + generated authorization + bundle
# + audit + outcome commit atomically; no independent approval transaction.
# Lease fencing prevents an expired worker from advancing a checkpoint. Recoverable stages replay.
# Do not hold transactions during source/artifact I/O, model inference, or human review.
@dataclass(frozen=True, kw_only=True)
class ParsedSourceProvider:
    name: str
    resolver: ParsedSourceResolver
    # Stable registration name matched by ParsedSourceOrigin.provider; registration does not invoke the resolver.
    # Caller-owned resolver/auth/pools are never copied or closed by the SDK.


# Read settings.configuration.model_gateway once; no separate gateway override or fallback.
# Instantiate inference extractors only when configured; deterministic capabilities remain usable.
```

```python
# src/domain_kernel/client.py
from __future__ import annotations

from domain_kernel._composition import ClientIntegrations
from domain_kernel._shared.domain.contracts import Page, ProjectInfo
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.configuration import ConfigurationInput
from domain_kernel.diagnostics import ConfigurationReport
from domain_kernel.modeling.domain.reference_packs import ReferencePack
from domain_kernel.project import Project


class Client:
    # Omitted/None config discovers cwd/domain-kernel.toml; genuine absence uses fresh defaults.
    # Explicit file paths load strictly; typed configuration bypasses discovery and file merging.
    # Delegate selection to PydanticConfigurationLoader; no parent/Git-root/global search or live reload.
    # Validate config/Env/policies and snapshot settings before binding; retain the exact gateway reference.
    # Configure it once via ClientConfiguration.model_gateway; existing handles share that capability.
    # No post-construction gateway replacement or duplicate Client-level gateway parameter.
    # Capture optional integrations once at startup; preserve host resource references without invoking them.
    # Existing handles reuse the registered parsed-source providers; no post-construction replacement.
    # Missing gateway fails only when an inference-dependent operation is invoked.
    # No network inference, source acquisition, schema migration, or project creation here.
    # No database I/O here. Omitted database settings enable lazy initialization at the first DB operation.
    # Explicit database settings (including SQLite()) require setup; injected transactions always own it.
    def __init__(
        self,
        *,
        config: ConfigurationInput | None = None,
        integrations: ClientIntegrations | None = None,
    ) -> None: ...

    def inspect_configuration(self) -> ConfigurationReport: ...
    # Redacted captured settings only; no I/O/probes. Never include gateway/resolver objects or credentials.
    # No public close lifecycle: SDK resources are operation-scoped and released on completion/failure.
    # Cancellation retains cleanup ownership until workers finish; host-owned resources are never closed.
    # Delegates to the internal Projects service; preserves its scope and behavior.
    async def create_project(
        self, *, actor: str, display_name: str | None = None, name: str | None = None
    ) -> Project: ...
    async def get_project(self, *, name: str) -> Project: ...
    async def list_projects(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ProjectInfo]: ...

    # Delegates to the internal ReferencePacks service; preserves its scope and behavior.
    async def get_reference_pack(self, *, key: str, version: str) -> ReferencePack: ...
    async def list_reference_packs(
        self, *, limit: int = 50, cursor: PageCursor | None = None
    ) -> Page[ReferencePack]: ...
```

```python
# src/domain_kernel/_database.py
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import override

from domain_kernel._composition import KernelTransaction
from domain_kernel._settings import RuntimeSettings
from domain_kernel._shared.application.persistence import UnitOfWorkFactory

# Planned: SQLAlchemy async ORM + aiosqlite are baseline; PostgreSQL/Psycopg is optional.
# Import SQLAlchemy/drivers only within the selected infrastructure adapter.
# Default operation-scoped engines use NullPool; close session and dispose engine on exit.
# Caller-owned pooled providers retain ownership; no Client.close() requirement is added.


class SQLiteUnitOfWorkFactory(UnitOfWorkFactory[KernelTransaction]):
    def __init__(self, *, settings: RuntimeSettings) -> None: ...
    # On async resource entry, await the private initialization gate before yielding adapters.
    # Enable it only for omitted database settings and this built-in factory; no DB I/O in construction.
    # Create directories/schema for a new/empty default DB; compatible existing schema is reused.
    # Serialize concurrent clients/processes; schema and version metadata commit atomically.
    # Unknown/partial/corrupt/incompatible schemas and storage/permission failures fail closed.
    # Never delete, migrate, overwrite, change paths, fall back to memory or bypass injected transactions.
    # Acquisition/setup occurs on async context entry, never at factory construction/call.
    # Yield fresh repositories and a TransactionManager sharing one clean AsyncSession.
    @override
    def __call__(self) -> AbstractAsyncContextManager[KernelTransaction]: ...


class PostgreSQLUnitOfWorkFactory(UnitOfWorkFactory[KernelTransaction]):
    def __init__(self, *, settings: RuntimeSettings) -> None: ...
    @override
    def __call__(self) -> AbstractAsyncContextManager[KernelTransaction]: ...


class SchemaManager:
    def __init__(self, *, settings: RuntimeSettings) -> None: ...
    # Internal initialization is shared by the lazy default gate and explicit operator setup.
    # Constructing Client performs no DB I/O; upgrades and all explicitly selected DB setup stay operator-owned.
    async def initialize(self) -> None: ...
    async def upgrade(self, *, target_version: str) -> None: ...


# Repository implementations:
# sources/infrastructure/repository.py: SQLiteSourceRepository, PostgreSQLSourceRepository
# discovery/infrastructure/repository.py: SQLiteDiscoveryRepository, PostgreSQLDiscoveryRepository
# reconciliation/infrastructure/repository.py: SQLiteReconciliationRepository, PostgreSQLReconciliationRepository
# review/infrastructure/repository.py: SQLiteReviewRepository, PostgreSQLReviewRepository
# modeling/infrastructure/repository.py: SQLiteModelRepository, PostgreSQLModelRepository
# Root catalog/idempotency implementations remain in _database.py.
```

```python
# src/domain_kernel/modeling/application/reference_packs.py
from __future__ import annotations

from collections.abc import Sequence

from domain_kernel.modeling.application.ports import ReferencePackComposer, SemanticReferenceMapper


class DeterministicReferencePackComposer(ReferencePackComposer):
    def __init__(self, *, semantic_mappers: Sequence[SemanticReferenceMapper] = ()) -> None: ...

    # Deterministic composition/diagnostics from explicit typed content; no LLM, catalog or DB.
```

```python
# src/domain_kernel/reference_packs.py
from __future__ import annotations

from domain_kernel.modeling.domain.reference_packs import (
    ReferencePack,
    ReferencePackBuild,
    ReferencePackSpec,
    ReferencePackValidation,
)

__all__ = ["ReferencePack", "ReferencePackBuild", "ReferencePackSpec", "ReferencePackValidation"]

# Value methods bind the built-in composer/codec at the SDK boundary, without a Client.
# Structural operations import no optional adapters; selected semantic mappings use private bindings.
# No standalone public aliases, transport or catalog writes. The host publishes immutable artifacts.
```

```python
# src/domain_kernel/bundles.py
from __future__ import annotations

from domain_kernel.modeling.domain.models import BundleValidation, DomainModelBundle


# Bundle value methods declared above use the same built-in codec as exports and this validation helper.
# No standalone serialization/schema aliases; domain records remain stdlib-only, codecs stay at the SDK boundary.
# No Client, configuration, I/O or audit effects; schema access is DomainModelBundle.get_json_schema().
def validate_bundle(*, bundle: DomainModelBundle) -> BundleValidation: ...
```

```python
# src/domain_kernel/notebook.py
from __future__ import annotations

from typing import Protocol

from domain_kernel._shared.domain.contracts import Artifact, Page
from domain_kernel._shared.domain.definitions import ChangeSet, Definition
from domain_kernel.diagnostics import ConfigurationReport
from domain_kernel.discovery.api.discovery import DiscoveryResult
from domain_kernel.modeling.api.modeling import (
    BundleValidation,
    Candidate,
    DomainModelBundle,
    ReferencePack,
    Publication,
    Readiness,
    ValidationReport,
)
from domain_kernel.modeling.domain.interchange import ProjectionAssessment
from domain_kernel.review.api.review import ReviewCase, ReviewImpact
from domain_kernel.sources.api.sources import (
    BatchIngestionResult,
    EvidenceContent,
    IngestedSource,
    SourceProfile,
)

type NotebookValue = (
    Definition
    | Page[Definition]
    | IngestedSource
    | BatchIngestionResult
    | DiscoveryResult
    | ReviewCase
    | Page[ReviewCase]
    | ReviewImpact
    | ChangeSet
    | ProjectionAssessment
    | Publication
    | Candidate
    | Readiness
    | ValidationReport
    | BundleValidation
    | DomainModelBundle
    | Artifact
    | ReferencePack
    | SourceProfile
    | EvidenceContent
    | ConfigurationReport
)


class NotebookRenderer(Protocol):
    def html(self, *, value: NotebookValue) -> str: ...


# Optional presentation integration; ordinary notebook value display is the primary inspection path.
# Synchronous, bounded rendering of supplied snapshots only: no persistence reads, inference,
# evidence acquisition, writes, callbacks or automatic transitions. Escape content and validate URLs.
def render_notebook(*, value: NotebookValue, renderer: NotebookRenderer | None = None) -> str: ...
def enable_notebook_display(*, renderer: NotebookRenderer | None = None) -> None: ...
def disable_notebook_display() -> None: ...


# Only enable requires the optional notebook runtime; importing the SDK never imports IPython.
# Disable restores prior formatters; rendering reveals excerpts only from explicitly loaded EvidenceContent.
# Registration is repeat-safe within the active kernel and preserves the original formatters.
# Include meaningful text/plain fallbacks; HTML/custom widget support is never required for SDK use.
# Respect frontend notebook-trust behavior; artifact views show supplied metadata, never download bytes.
# Show captured identity/revision, bounded page counts and continuation, never invented totals/live state.
# Custom renderers obey the same no-I/O, escaping, resource-bound and secret-redaction contract.
# Interactive selection/forms/callbacks live in the notebook application, outside this renderer.
# Callbacks use normal async SDK operations with inspected revisions, actors and stable retry intent;
# explicit preview/submit and code-cell alternatives preserve the ordinary review/publication gates.
```

The [primary notebook journey](ARCHITECTURE.md#the-legislative-domain-model-notebook-journey)
is a versioned example application and executable teaching/product-acceptance
surface. A developer at a lobbying organisation uses real AI-in-recruitment documents
and pinned ELI/DPV resources to build a reusable legislative domain model; optional
LOMO and formal exercises use the existing ontology, review and adapter contracts.
The corpus, chapter structure, rerun/resume behavior and optional controls introduce
no parallel domain API or storage model. Legislative analysis and operational
records remain downstream; the tour ends with independent bundle consumption and
supported projections. Extend this display union and its conformance tests when a new
inspectable capability is added; basic display starts with the manual-model slice.
The [capability coverage map](ARCHITECTURE.md#notebook-capability-coverage) assigns
advanced exercises and specialist recipes, including formal semantics, rich shapes,
pack/dependency evolution, alternate evidence inputs, LinkML import and recovery.
C4 teaches additional instructions over the full AI Act and an isolated full override,
inspects DiscoveryPrompt captures, and preserves the SDK response schema and existing
failure/recovery rules. Prompt guidance is not deterministic passage selection.
Label replayed/pre-parsed public-corpus fixtures and authored failure cases; keep
live semantic-quality checks distinct from deterministic conformance results.
The [notebook delivery contract](ARCHITECTURE.md#portable-delivery-and-continuous-acceptance)
owns frontend coverage, execution tests and dependency isolation.

The [temporary interactive preview](examples/notebooks/README.md) keeps disabled
planned calls beside labelled fixture execution. Its example-only views and branch
controls introduce no SDK signatures, replacement client or persistence layer.
Local practice controls compare bounded authored answers and show explanations; they do not
execute entered text, submit reviews or introduce SDK grading methods.
The shared catalogue contains only presentation expectations: identity/revision,
shape selections, evidence, review outcomes and named snapshots. A structured
obligation card presents existing rules and evidence; it adds no legal-rule API.
Field-level basis/citation labels are teaching annotations, not new
`AttributeDefinition` parameters. Curated export excerpts are checked against the
same definitions without implementing a second exporter. Required manual criteria
remain UNKNOWN; recorded human judgement never silently changes their requirement
or turns them into executable proof.
The Article 13 consumer example uses existing bundle `get_concept()`, direct
`get_attribute()`, `content.definitions` and `evidence` inspection. Evidence citations
do not embed source excerpts; field-level teaching annotations stay in the preview.
Diagram/matrix selection and expandable details only inspect the captured snapshot.
Syntax and documented-keyword checks are not runtime SDK validation. As each owning
issue lands, connect real results to the presentation and remove that operation's
fixture dependency; never silently fall back to a mock when a real call fails.

```python
# src/domain_kernel/__init__.py
from __future__ import annotations

from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel.shared.identifiers.audit_id import AuditId

from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel._shared.domain.model_values import (
    BusinessCode,
    LabelText,
    MeaningText,
    LanguageTag,
    Count,
    DecimalPrecision,
    DecimalScale,
    CollectionKind,
    Nullability,
    ValueSetMembership,
    LabelRole,
    LocalizedLabel,
    LocalizedDescription,
    Terminology,
    CardinalityBounds,
    RelationshipCardinality,
    DecimalFacets,
)
from domain_kernel._shared.domain.data_shapes import (
    ScalarValueType,
    ConceptReferenceType,
    ValueSetType,
    StructuredValueType,
    AttributeType,
    KeyDefinition,
    QuantityBinding,
)
from domain_kernel._shared.domain.dependencies import (
    DependencyRemapping,
    DependencyChangeRequest,
)
from domain_kernel._shared.domain.acceptance import (
    CheckRequirement,
    CheckOutcome,
    DistinctDefinitionsCheck,
    QuantityRequiredCheck,
    ManualCriterion,
    AcceptancePredicate,
    AcceptanceCheckDefinition,
    AcceptanceCheckResult,
)
from domain_kernel._shared.domain.definitions import (
    ValueSetDefinition,
    ValueSetMember,
    UnitDefinition,
    StructuredValueDefinition,
)
from domain_kernel._shared.domain.contracts import (
    KeyEnforcementObligation,
    ReferenceTargetObligation,
    RelationshipEnforcementObligation,
    ConsumerObligation,
    CollectionSemanticsObligation,
)
from domain_kernel.modeling.domain.models import (
    DependencyChange,
)
from domain_kernel.modeling.domain.interchange import (
    JsonSchemaProjectionRequest,
)

from domain_kernel._shared.domain.ontology_assets import (
    OntologySyntax,
    OntologyEntityKind,
    SemanticRelation,
    OntologyDocumentPin,
    OntologyTermReference,
    OntologyDocument,
    ParsedOntology,
    OntologyImportBinding,
    OntologyContextBinding,
    OntologyClosurePin,
    OntologyClosure,
    OntologyLimits,
)

from domain_kernel._shared.domain.definitions import (
    ModelTermReference,
    SemanticLinkDefinition,
    OntologyModuleDefinition,
)

from domain_kernel.modeling.domain.semantics import (
    ReasoningProfile,
    SemanticRegime,
    ReasoningTask,
    SemanticStatus,
    ModuleExtractionMethod,
    ModuleGuarantee,
    ModuleExtractionSupport,
    ReasoningSupport,
    OntologyCapabilities,
    ReasoningRequest,
    ReasoningResult,
    OntologyModuleResult,
)

from domain_kernel.modeling.application.ontology import (
    OntologyAdapter,
    OntologyReasoner,
    OntologyModuleExtractor,
)

from domain_kernel.ontologies import (
    load_ontology,
    reason_ontology,
    extract_ontology_module,
)

from domain_kernel.modeling.domain.composition import (
    TraversalDirection,
    ModelComposition,
    SliceDefinition,
    ModelSlice,
)

from domain_kernel.composition import (
    compose_models,
    slice_model,
)

from domain_kernel.ontologies import (
    ReasoningModelValidator,
)

from domain_kernel.errors import (
    InvalidOntologyError,
)


from domain_kernel.authoring import (
    DomainModelBuilder,
    UNSET,
    Unset,
)
from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    MapToPlannedDefinition,
    CreateDefinition,
    ReviseDefinition,
    RetireDefinition,
    RestoreDefinition,
    CorrectMapping,
    IncludeCase,
    PlannedOperation,
    MappingCorrectionAction,
    ModelChangePlan,
)
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel._shared.domain.contracts import (
    SchemaOrigin,
    SemanticArtifactMetadata,
    CompanyDefinitionReference,
)
from domain_kernel._shared.domain.enums import (
    ConstraintTarget,
    RdfSyntax,
    LinkmlSyntax,
    SemanticGraphRole,
)
from domain_kernel.modeling.domain.interchange import (
    OpenValueSetAnnotation,
    UnitAnnotation,
    UnitBindingAnnotation,
    MappingDescriptor,
    ProjectionAssessment,
    ProjectionRequest,
    ProjectionAvailability,
    ProjectionFeature,
    ProjectionLocation,
    ProjectionFinding,
    ProjectionRemedy,
    RepresentationSupport,
    ValidationResponsibility,
    RdfProjectionRequest,
    LinkmlProjectionRequest,
    IdentityBinding,
    SemanticDocument,
    SemanticProjection,
    SemanticOntologyDependency,
    SchemaDocument,
    LinkmlProjection,
    SchemaImportResult,
)
from domain_kernel.interchange import (
    project_semantics,
    project_linkml,
    load_linkml,
)
from domain_kernel.errors import (
    InvalidChangePlanError,
    InvalidSchemaError,
)

from domain_kernel._shared.domain.enums import (
    AlignmentLayer,
    AlignmentStatus,
    CaseKind,
    CaseStatus,
    ComparisonKind,
    Compatibility,
    ConfirmationMethod,
    ConstraintLanguage,
    DataType,
    DefinitionChangeKind,
    DefinitionKind,
    DefinitionOrigin,
    DefinitionStatus,
    EventKind,
    EvidenceBasis,
    ExportFormat,
    FlowKind,
    GatewayDirection,
    GatewayKind,
    HitPolicy,
    InferredColumnType,
    IssueSeverity,
    MappingRelation,
    ModelKind,
    ObligationKind,
    OntologyFormat,
    PackMaturity,
    QuestionDisposition,
    ReferenceAssetKind,
    ReferenceDispositionKind,
    RequirementKind,
    ReviewActionKind,
    RunStatus,
    ScalarDataType,
    SourceDisposition,
    StatementForm,
    StatementIntent,
)

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.reconciliation.domain.identifiers.alignment_suggestion_id import (
    AlignmentSuggestionId,
)
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId


from domain_kernel._composition import (
    ClientIntegrations,
    ParsedSourceProvider,
    ReaderBinding,
    StoreBinding,
)
from domain_kernel._shared.application.inference import ModelGateway, ModelRequest, ModelResponse
from domain_kernel._shared.domain.contracts import (
    Artifact,
    CandidatePin,
    CellRange,
    DefinitionReference,
    DocumentSpan,
    Evidence,
    ExternalLocation,
    ModelScope,
    ModelVersion,
    Page,
    Person,
    PinnedDefinitionReference,
    ReferencePackPin,
    SnapshotReference,
    SourceRevision,
    StatementSpan,
    ParsedSourceOrigin,
)
from domain_kernel._shared.domain.definitions import (
    Activity,
    AttributeDefinition,
    BusinessDecisionDefinition,
    ChangeSet,
    Concept,
    ConceptDefinition,
    Condition,
    ConstraintDefinition,
    DecisionInput,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    Definition,
    DefinitionCorrespondence,
    Event,
    Flow,
    Gateway,
    Process,
    ProcessDefinition,
    ProcessNodeId,
    ReferenceAlignment,
    ReferenceDisposition,
    ReferenceDispositionChange,
    RelationshipDefinition,
    Role,
    RuleDefinition,
    SourceAlignment,
    SourceAlignmentChange,
)
from domain_kernel._shared.domain.ontology import BlankNode, Iri, OntologyStatement, RdfLiteral
from domain_kernel.bundles import validate_bundle
from domain_kernel.client import Client
from domain_kernel.configuration import ClientConfiguration
from domain_kernel.discovery.api.discovery import (
    DiscoveryFailure,
    DiscoveryPrompt,
    DiscoveryResult,
    Proposal,
)
from domain_kernel.errors import (
    ArtifactConflictError,
    AuthenticationError,
    ConfigurationError,
    DomainKernelError,
    EvidenceUnavailableError,
    IdempotencyConflictError,
    InferenceError,
    InvalidBundleError,
    InvalidDecisionError,
    MissingCapabilityError,
    MissingDependencyError,
    AttributeNotFoundError,
    KeyNotFoundError,
    ProcessPartNotFoundError,
    ProcessPartAlreadyExistsError,
    AttributeAlreadyExistsError,
    KeyAlreadyExistsError,
    DefinitionNotFoundError,
    DefinitionAlreadyExistsError,
    DefinitionKindMismatchError,
    ModelNotFoundError,
    ModelAlreadyExistsError,
    OperationInProgressError,
    ReferencePackNotFoundError,
    PatternNotFoundError,
    InvalidReferencePackError,
    UnsupportedReferencePackVersionError,
    ProjectNotFoundError,
    ProjectAlreadyExistsError,
    PublicationBlockedError,
    ProjectionBlockedError,
    PublicationNotFoundError,
    ResourceLimitError,
    ScopeMismatchError,
    SourceRevisionMismatchError,
    SourceNotFoundError,
    SourceAlreadyExistsError,
    SourceUnavailableError,
    StaleStateError,
    UnsupportedBundleVersionError,
    UnsupportedCapabilityError,
    VersionExistsError,
)
from domain_kernel.modeling.api.modeling import (
    Approval,
    BundleValidation,
    Candidate,
    DefinitionBinding,
    DomainModelBundle,
    Model,
    ModelInfo,
    Pattern,
    ReferencePack,
    ReferencePackSpec,
    ReferencePackImport,
    ReferencePackBuild,
    ReferencePackValidation,
    ReferencePackChange,
    ReferenceOrigin,
    ReferencePackDependency,
    ReferenceDefinition,
    ReferencePackObligation,
    Publication,
    Readiness,
)
from domain_kernel.notebook import (
    NotebookRenderer,
    disable_notebook_display,
    enable_notebook_display,
    render_notebook,
)
from domain_kernel.diagnostics import (
    ConfigurationSource,
    DatabaseInitialization,
    ConfigurationSetting,
    ConfigurationReport,
)
from domain_kernel.project import Project
from domain_kernel.review.api.review import (
    Accept,
    AnswerQuestion,
    ApproveLocalExtension,
    Confirmation,
    ConfirmStatement,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    MapToDefinition,
    MapToReference,
    Reject,
    ReviewCase,
    CaseDecision,
    ReviewDecision,
    ReviewImpact,
    ReviewReceipt,
    ReviewRequirement,
)
from domain_kernel.sources.api.sources import (
    CSV,
    PDF,
    CopyTo,
    Excel,
    IngestedSource,
    ParsedGraph,
    ParsedPart,
    ParsedPayload,
    ParsedSource,
    ParsedSourceResolver,
    ParsedTable,
    ParsedText,
    Ontology,
    ReaderLocation,
    SourceDescriptor,
    SourceInput,
    SourceFolder,
    IngestionStage,
    IngestionSuccess,
    IngestionFailure,
    BatchIngestionResult,
    Statement,
    Word,
)

__all__ = [
    "AttributeId",
    "KeyId",
    "RoleId",
    "ActivityId",
    "EventId",
    "GatewayId",
    "FlowId",
    "ConditionId",
    "BusinessCode",
    "LabelText",
    "MeaningText",
    "LanguageTag",
    "Count",
    "DecimalPrecision",
    "DecimalScale",
    "CollectionKind",
    "Nullability",
    "ValueSetMembership",
    "LabelRole",
    "LocalizedLabel",
    "LocalizedDescription",
    "Terminology",
    "CardinalityBounds",
    "RelationshipCardinality",
    "DecimalFacets",
    "ScalarValueType",
    "ConceptReferenceType",
    "ValueSetType",
    "StructuredValueType",
    "AttributeType",
    "KeyDefinition",
    "QuantityBinding",
    "DependencyRemapping",
    "DependencyChangeRequest",
    "CheckRequirement",
    "CheckOutcome",
    "DistinctDefinitionsCheck",
    "QuantityRequiredCheck",
    "ManualCriterion",
    "AcceptancePredicate",
    "AcceptanceCheckDefinition",
    "AcceptanceCheckResult",
    "ValueSetDefinition",
    "ValueSetMember",
    "UnitDefinition",
    "StructuredValueDefinition",
    "KeyEnforcementObligation",
    "ReferenceTargetObligation",
    "RelationshipEnforcementObligation",
    "ConsumerObligation",
    "CollectionSemanticsObligation",
    "DependencyChange",
    "JsonSchemaProjectionRequest",
    "OntologySyntax",
    "OntologyEntityKind",
    "SemanticRelation",
    "OntologyDocumentPin",
    "OntologyTermReference",
    "OntologyDocument",
    "ParsedOntology",
    "OntologyImportBinding",
    "OntologyContextBinding",
    "OntologyClosurePin",
    "OntologyClosure",
    "OntologyLimits",
    "ModelTermReference",
    "SemanticLinkDefinition",
    "OntologyModuleDefinition",
    "ReasoningProfile",
    "SemanticRegime",
    "ReasoningTask",
    "SemanticStatus",
    "ModuleExtractionMethod",
    "ModuleGuarantee",
    "ModuleExtractionSupport",
    "ReasoningSupport",
    "OntologyCapabilities",
    "ReasoningRequest",
    "ReasoningResult",
    "OntologyModuleResult",
    "OntologyAdapter",
    "OntologyReasoner",
    "OntologyModuleExtractor",
    "load_ontology",
    "reason_ontology",
    "extract_ontology_module",
    "TraversalDirection",
    "ModelComposition",
    "SliceDefinition",
    "ModelSlice",
    "compose_models",
    "slice_model",
    "ReasoningModelValidator",
    "InvalidOntologyError",
    "SemanticArtifactMetadata",
    "MapToPlannedDefinition",
    "DomainModelBuilder",
    "UNSET",
    "Unset",
    "AuthoredContent",
    "CreateDefinition",
    "ReviseDefinition",
    "RetireDefinition",
    "RestoreDefinition",
    "CorrectMapping",
    "IncludeCase",
    "PlannedOperation",
    "MappingCorrectionAction",
    "ModelChangePlan",
    "ChangePlanId",
    "SchemaOrigin",
    "CompanyDefinitionReference",
    "ConstraintTarget",
    "RdfSyntax",
    "LinkmlSyntax",
    "SemanticGraphRole",
    "OpenValueSetAnnotation",
    "UnitAnnotation",
    "UnitBindingAnnotation",
    "MappingDescriptor",
    "ProjectionAssessment",
    "ProjectionRequest",
    "ProjectionAvailability",
    "ProjectionFeature",
    "ProjectionLocation",
    "ProjectionFinding",
    "ProjectionRemedy",
    "RepresentationSupport",
    "ValidationResponsibility",
    "RdfProjectionRequest",
    "LinkmlProjectionRequest",
    "MappingId",
    "IdentityBinding",
    "SemanticDocument",
    "SemanticProjection",
    "SemanticOntologyDependency",
    "SchemaDocument",
    "LinkmlProjection",
    "SchemaImportResult",
    "project_semantics",
    "project_linkml",
    "load_linkml",
    "InvalidChangePlanError",
    "InvalidSchemaError",
    "ReviewActionKind",
    "AlignmentId",
    "AlignmentSuggestionId",
    "AuditId",
    "AuditAction",
    "AuditOutcome",
    "AuditRecord",
    "AuditResource",
    "ApprovalId",
    "BundleId",
    "CandidateId",
    "ContentHash",
    "DecisionId",
    "DefinitionId",
    "DiscoveryDraftId",
    "DiscoveryRunId",
    "EvidenceId",
    "ModelId",
    "ObligationId",
    "PageCursor",
    "PatternId",
    "PersonId",
    "ProjectId",
    "ProposalId",
    "PublicationId",
    "QuestionId",
    "ReferenceDefinitionId",
    "ReviewCaseId",
    "SourceId",
    "SourceManifestId",
    "SourceRevisionId",
    "ValidationReportId",
    "AlignmentLayer",
    "AlignmentStatus",
    "CaseKind",
    "CaseStatus",
    "ComparisonKind",
    "Compatibility",
    "ConfirmationMethod",
    "ConstraintLanguage",
    "DataType",
    "DefinitionChangeKind",
    "DefinitionKind",
    "DefinitionOrigin",
    "EventKind",
    "EvidenceBasis",
    "ExportFormat",
    "FlowKind",
    "GatewayDirection",
    "GatewayKind",
    "HitPolicy",
    "InferredColumnType",
    "IssueSeverity",
    "MappingRelation",
    "ObligationKind",
    "OntologyFormat",
    "PackMaturity",
    "QuestionDisposition",
    "ReferenceAssetKind",
    "ReferenceDispositionKind",
    "RequirementKind",
    "RunStatus",
    "ScalarDataType",
    "SourceDisposition",
    "StatementForm",
    "StatementIntent",
    "NotebookRenderer",
    "disable_notebook_display",
    "enable_notebook_display",
    "render_notebook",
    "hello",
    "ModelGateway",
    "ModelRequest",
    "ModelResponse",
    "Artifact",
    "Evidence",
    "ModelScope",
    "ModelVersion",
    "Page",
    "Person",
    "ReferencePackPin",
    "SourceRevision",
    "CandidatePin",
    "DefinitionReference",
    "PinnedDefinitionReference",
    "SnapshotReference",
    "CellRange",
    "DocumentSpan",
    "ExternalLocation",
    "StatementSpan",
    "ParsedSourceOrigin",
    "Activity",
    "AttributeDefinition",
    "BusinessDecisionDefinition",
    "ChangeSet",
    "Concept",
    "ConceptDefinition",
    "Condition",
    "ConstraintDefinition",
    "DecisionInput",
    "DecisionOutput",
    "DecisionRule",
    "Definition",
    "DefinitionCorrespondence",
    "DefinitionStatus",
    "Event",
    "Flow",
    "Gateway",
    "Process",
    "ProcessDefinition",
    "ProcessNodeId",
    "ReferenceAlignment",
    "ReferenceDisposition",
    "ReferenceDispositionChange",
    "SourceAlignment",
    "SourceAlignmentChange",
    "RelationshipDefinition",
    "Role",
    "RuleDefinition",
    "DecisionValue",
    "BlankNode",
    "Iri",
    "OntologyStatement",
    "RdfLiteral",
    "Client",
    "ConfigurationSource",
    "DatabaseInitialization",
    "ConfigurationSetting",
    "ConfigurationReport",
    "ClientConfiguration",
    "DiscoveryFailure",
    "DiscoveryPrompt",
    "DiscoveryResult",
    "Proposal",
    "ArtifactConflictError",
    "AuthenticationError",
    "ConfigurationError",
    "DomainKernelError",
    "EvidenceUnavailableError",
    "IdempotencyConflictError",
    "InferenceError",
    "InvalidDecisionError",
    "MissingDependencyError",
    "AttributeNotFoundError",
    "KeyNotFoundError",
    "ProcessPartNotFoundError",
    "ProcessPartAlreadyExistsError",
    "AttributeAlreadyExistsError",
    "KeyAlreadyExistsError",
    "DefinitionNotFoundError",
    "DefinitionAlreadyExistsError",
    "DefinitionKindMismatchError",
    "ModelNotFoundError",
    "ModelAlreadyExistsError",
    "OperationInProgressError",
    "ReferencePackNotFoundError",
    "PatternNotFoundError",
    "InvalidReferencePackError",
    "UnsupportedReferencePackVersionError",
    "ProjectNotFoundError",
    "ProjectAlreadyExistsError",
    "PublicationBlockedError",
    "ProjectionBlockedError",
    "PublicationNotFoundError",
    "ResourceLimitError",
    "ScopeMismatchError",
    "SourceRevisionMismatchError",
    "SourceNotFoundError",
    "SourceAlreadyExistsError",
    "SourceUnavailableError",
    "StaleStateError",
    "UnsupportedCapabilityError",
    "VersionExistsError",
    "InvalidBundleError",
    "MissingCapabilityError",
    "UnsupportedBundleVersionError",
    "Approval",
    "Candidate",
    "DomainModelBundle",
    "Model",
    "ModelInfo",
    "ModelKind",
    "ReferencePack",
    "ReferencePackSpec",
    "ReferencePackImport",
    "ReferencePackBuild",
    "ReferencePackValidation",
    "ReferencePackChange",
    "ReferenceOrigin",
    "Publication",
    "Readiness",
    "BundleValidation",
    "DefinitionBinding",
    "Pattern",
    "ReferencePackDependency",
    "ReferenceDefinition",
    "ReferencePackObligation",
    "Project",
    "Accept",
    "AnswerQuestion",
    "ApproveLocalExtension",
    "ConfirmStatement",
    "Defer",
    "EditDefinition",
    "Exclude",
    "KeepNonblockingQuestion",
    "MapToDefinition",
    "MapToReference",
    "Reject",
    "ReviewCase",
    "CaseDecision",
    "ReviewDecision",
    "ReviewImpact",
    "ReviewReceipt",
    "ReviewRequirement",
    "Confirmation",
    "CSV",
    "PDF",
    "CopyTo",
    "Excel",
    "IngestedSource",
    "Ontology",
    "ReaderLocation",
    "SourceDescriptor",
    "SourceInput",
    "SourceFolder",
    "IngestionStage",
    "IngestionSuccess",
    "IngestionFailure",
    "BatchIngestionResult",
    "Statement",
    "Word",
    "ParsedGraph",
    "ParsedPart",
    "ParsedPayload",
    "ParsedSource",
    "ParsedSourceResolver",
    "ParsedTable",
    "ParsedText",
    "ClientIntegrations",
    "ParsedSourceProvider",
    "ReaderBinding",
    "StoreBinding",
    "validate_bundle",
]


def hello() -> str: ...  # Preserve the existing engineering-baseline export.
```

## Batch ingestion contract

`Project.ingest_sources()` delegates to `Sources.ingest_many()` with exact signature parity.
Use the architecture's [batch/folder contract](ARCHITECTURE.md#batch-ingestion-and-folder-selection)
for glob, naming, overlap, enumeration-budget and replay semantics. Validate/freeze a
nonempty input sequence and positive integer overrides before I/O. Overrides may only
lower the configured limits. A fixed worker pool shares the client's capacity with
individual ingestion calls; listing and blocking parsers also respect bounded capacity.
No database transaction spans provider I/O; each successful source commits independently.

Expand folders completely before content ingestion; listing failure produces a LISTING
outcome and no files from that folder, while independent selections can proceed. A
batch-wide file/entry/time limit aborts content ingestion, never truncates success.
Explicit conflicting names/keys fail preflight; discovered name collisions mark every
affected file NAMING and ingest none of them. Existing catalog-name conflicts and
document/provider errors become per-item failures. Fatal coordination/persistence errors
and cancellation propagate after worker cleanup; prior durable commits remain.
Equivalent overlaps share one ingestion/audit and bind all corresponding item keys to
the same outcome atomically; conflicting names/options/provider pins fail without choosing a winner.
Original selection manifests stay immutable when computing a combined batch result.
Conflicting explicit requests fail preflight; exact repeated requests coalesce. Claim
all equivalent item keys before processing, and verify any stored outcome against all
request/pin guards before attaching aliases; never create a duplicate success audit.

Persist complete folder manifests, including unresolved per-file issues, under the
scoped folder invocation using existing lease/fencing primitives. Child inputs receive
stable keys before processing; matching successful retries replay before acquisition.
Item keys use the ordinary ingest_source operation scope; folder keys use
capture_source_manifest. No aggregate batch key changes replay when retrying a subset.
Transient failures remain retryable, not permanently cached successes. A failed listing
may be retried until a complete manifest is captured; it never freezes a partial folder.
Manifests retain provider identities/version tokens where available, not a global folder
snapshot. Without such tokens, bytes are pinned on acquisition; successful revision
digests remain authoritative. CAPTURE_SOURCE_MANIFEST audit pins SourceManifestId/hash;
child ingestion events link to that capture. Operational manifests are not bundle content.
For overlaps, retain the primary capture as parent and the other manifest pins as audit
resource references. Register the source_manifest outcome codec for durable replay.

## Projection and convenience contract boundaries

The factory signatures above construct the existing records; all nominal input types,
keyword-only arguments and explicit review boundaries remain in force. Unit helpers
create independently reusable definitions. Quantity helpers create one structured value
using an explicit closed unit set and optional quantity-kind term, with no lookup,
adoption, conversion or generated unit/value-set identity. Inline units need no ontology.

Unit records, nullable quantity kinds, typed unit annotations and reference traversal extend
the unreleased 1.0 wire/mapping drafts together. Register their capabilities and closed
schemas before advertising support; unsupported readers/mappers must reject, not drop them.
Once released, incompatible wire or mapping changes require new registered versions.
Preflight reports UNIT_DEFINITION/UNIT_REFERENCE/QUANTITY_BINDING findings, including
annotation-only representation; generic consumers need not interpret SDK metadata.

Projection assessment dispatches to the existing mapping ports. Export uses that same
analysis, reports unsupported essential semantics before writing, and preserves the
exact consumer obligations. Native exact string/code set checks in JSON Schema and
RDF/SHACL do not emit `CollectionSemanticsObligation`; numeric/date/reference cases
retain it conservatively, as do initial LinkML set projections. This conditional rule
never removes key, reference-resolution or relationship obligations.

`dk:open_value_set` uses the typed `OpenValueSetAnnotation` record on a permissive
LinkML string type, not a closed enum. Known codes are annotations; ordinary LinkML
consumers need not interpret them. Import validates metadata and rejects narrowing
conflicts, unknown versions or conflicting copies. No annotation triggers resource
fetches or authorizes model changes.

## Optional integration roadmap boundary

The architecture's [optional interoperability roadmap](ARCHITECTURE.md#optional-interoperability-roadmap)
contains QUDT/UCUM tooling, SSSOM, R2RML/CSVW, industrial adapters, RDFC-1.0, DCAT 3
and wider mapping/query capabilities. This reference deliberately adds no speculative
provider interfaces or dependencies for them. Existing ontology terms, reference packs,
validator/exporter ports and typed consumer obligations are their integration boundaries.

Ordered RDF lists, null-in-RDF, decimal-facet projection and arbitrary OWL-to-schema
conversion remain deferred versioned mappings. Static annotated open LinkML sets
are part of the initial bounded mapping; dynamic vocabularies remain deferred.
