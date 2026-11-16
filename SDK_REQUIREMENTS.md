# Domain Kernel SDK — Requirements

**Proposed API and contracts; not implemented.** Python 3.13+; Apache-2.0.
[ARCHITECTURE.md](ARCHITECTURE.md) is the single source of truth. These recipes and
[INTERFACES.md](INTERFACES.md) elaborate its behavior without adding product scope.

Domain Kernel turns source evidence, human knowledge and reference definitions into
editable, reconciled, validated and versioned business domain models with provenance.
It is an embeddable, headless Python SDK for establishing and correcting business
meaning, with portable models as its output.

**FDE Workbench**, **ERP** and **Inframeld GraphRAG** are independent applications.
Each can create, edit and publish its own models; there is no Workbench-to-ERP handoff
or required shared application database/service. Applications own user journeys,
business choices, identity/authorization, indexing, instance graphs, execution and
documentation. The ERP owns its configurable rule engine and activation/migrations;
Inframeld owns instance/fact extraction, resolution, graph population and retrieval.

The SDK owns model integrity and provenance within declared scope and supported
semantics. Stable model contracts describe concepts, relationships, constraints,
processes and decisions. They establish no guarantee of business truth or runtime behaviour.

The [manufacturing walkthrough](ARCHITECTURE.md#manufacturing-walkthrough-from-pdfs-to-a-reviewed-model)
explains the complete journey. A model's graph connects **definitions**, such as
`Machine`, `WorkOrder` and their relationship. Actual assets, work orders and their
links are **instance data** maintained by the consuming application. Typed SDK
records are authoritative, persisted through SQLite or optional PostgreSQL; the
complete portable representation is the published JSON bundle. RDF and LinkML are
derived views, not alternative editable stores.

Original ontology terms, formal imports/inheritance, optional reasoning and graph
granularity follow the architecture's
[ontology-resource contract](ARCHITECTURE.md#original-ontology-terms-and-immutable-semantic-resources),
[semantic capability contract](ARCHITECTURE.md#semantic-links-inheritance-and-reasoning-capabilities)
and [model composition guidance](ARCHITECTURE.md#domain-modules-enterprise-compositions-and-workflow-views).
Supporting a source syntax does not establish support for every inference task.

Python examples use explicit keyword arguments, and proposed SDK parameters are
keyword-only. Standalone value expressions indicate values to inspect in a notebook.

### Start small, then add capabilities

Start with the architecture's [complete quickstart](ARCHITECTURE.md#quickstart-create-review-and-publish-a-model)
and [progressive guide](ARCHITECTURE.md#grow-the-model-step-by-step): a reviewed model,
fields/corrections, reusable business meanings, evidence/discovery, projection
assessment, then model evolution and composition. The numbered sections here are
independent task recipes, not one sequential program. Each retains its own named
inputs and explicit review prerequisites. Full low-level constructors remain in
[INTERFACES.md](INTERFACES.md).

The [Domain Kernel Tour](ARCHITECTURE.md#the-legislative-domain-model-notebook-journey)
is the continuous, executable teaching and product-acceptance journey. A developer
at a lobbying organisation builds a reusable domain model for legislative-analysis
software about AI in recruitment, using real documents and ontologies. The
independent recipes here remain complementary references.

### Python API conventions

Use the architecture's [flat public API](ARCHITECTURE.md#flat-public-api): direct
methods on `Client`, `Project` and `Model`. For example, `client.get_project`,
`project.get_model`, `project.ingest_source`, `model.get_definition`,
`model.propose_change_plan`, `model.preview_changes` and `model.decide_review`.
The scope comes from the handle; parameters identify the resource within it.
There are no public grouped-service aliases. Typed data attributes, the builder and
standalone value/interop functions keep their existing roles. Internal service
boundaries do not become consumer-facing collection properties.

Await all persistence-facing operations, including catalog creation/lookups, review
pages, previews, comparisons, submission, publication and export. Both SQLite and
PostgreSQL follow the same async contract; read-only does not mean I/O-free.
Builders, decision constructors, loaded snapshot getters/properties and in-memory
serialization/projection stay synchronous. Handle properties never trigger hidden
database reads; reload through the relevant async lookup to obtain a fresh snapshot.
Client construction and configuration loading are synchronous startup operations
without database access. In scripts, run SDK operations inside an async function;
notebooks may use top-level `await`.

Closed choices use `StrEnum` members; fixed record tags remain `Literal` discriminators.
Use `DataType.STRING`, `CaseStatus.PENDING`, and other exported named values in Python.
Wire/config inputs use their stable strings and are explicitly decoded and validated.
Resource IDs are distinct value types; pass SDK-returned IDs through unchanged, or
reconstruct external input with `ReviewCaseId(value=received_case_id)`. A definition ID
cannot substitute for a review-case ID. Names, prose, decision-local expression keys and extensible
registry labels remain validated strings. New shape and terminology contracts use
nominal value objects, including `AttributeId`, `KeyId`, `BusinessCode`,
`Count`, `LanguageTag`, `LabelText` and `MeaningText`; Python does not accept raw
primitive substitutes for these fields. See the architecture's
[defaults and type conventions](ARCHITECTURE.md#defaults-and-python-type-conventions).

Convenience factories preserve those types: `AttributeDefinition.string`, `.decimal`,
`.reference` and `.value_set` return the ordinary record with `required`, `collection`,
`min_items` and `max_items`. Required presence is independent of collection size; counts remain
typed `Count` values. No primitive coercion or alternate builder model is introduced.
`.value_set(value_set=...)` takes a typed `DefinitionReference` and constructs
`ValueSetType` without creating or copying the referenced value set.
`DomainModelBuilder.add_unit` creates a reusable unit with optional symbol and ontology term.
`.add_value_set` requires an explicit membership policy and typed members; member `unit`
references bind planned IDs or inspected snapshots supplied through `referenced_definitions`.
`.add_quantity` adds one structured value with required decimal `magnitude`, required `unit`
and a `QuantityBinding`; its closed unit set is explicit and `quantity_kind` defaults to `None`.
Inline unit members need no ontology; every supplied term retains its verified source pin. Full constructors remain
available for specialized shapes. All proposals still need explicit review.

Optional capabilities default to `None`; optional collections default to empty.
Public methods, factories and record/configuration constructors accept `Sequence[T]`:
lists or tuples, with lists used in examples. They validate and immediately copy
collections into immutable tuples, including nested sequences, so later caller
mutation cannot alter a captured record or plan. Read-only `Sequence[T]` record
annotations still hold tuples at runtime. Fixed-position pairs remain tuples and
signature defaults remain `()`, never mutable lists. Strings/bytes, sets and
one-shot iterators are not collection inputs (`aliases=["Part"]`, not `aliases="Part"`). Required meaning,
authority and concurrency choices stay explicit. Full replacement revisions use
empty collections as replacement values, not “preserve existing.”

```python
from domain_kernel import Client, ModelKind

client = Client()  # Omitted database: initialize default SQLite on first database use.
project = await client.create_project(actor="user:model-editor", display_name="Minimal Example")
model = await project.create_model(
    actor="user:model-editor",
    display_name="Component Catalog",
    description="Component types, suppliers and inventory terms for purchasing and manufacturing.",
    kind=ModelKind.PROPOSED,
)
# Pass reference_pack=selected_pack only when you want that pack's content/checks.
```

Project and model creation use `display_name` to generate a stable lookup `name`.
An explicit `name` overrides generation; a name-only call uses that string as its
display label. For example, these independent projects illustrate both forms:

```python
regional_project = await client.create_project(
    actor="user:model-editor",
    display_name="Example Company — European Operations",
    name="example-eu",
)
named_project = await client.create_project(actor="user:model-editor", name="example-us")
```

The same naming inputs apply to `create_model`, with an explicit `kind` and non-blank
`description` explaining the business area, intended use and relevant exclusions.
Definitions record their meaning and specific qualifications in `meaning`; they do
not copy or override the model description. Published snapshots retain the description.
Display labels need not be unique; lookup names must be unique within their scope.
Duplicate creation raises `ProjectAlreadyExistsError` or `ModelAlreadyExistsError`,
without suffixing or returning the existing resource. Reopen with `get_project(name=...)`
or `get_model(name=...)`. See the [naming contract](ARCHITECTURE.md#project-and-model-names)
for generation, validation and identity rules.

Model-owned definitions use the same `display_name`, optional `name` and generated
ID convention. Lookup names are unique across definition kinds within their model,
including reserved names of removed definitions; display labels may repeat. Typed
`get_concept(name=...)` returns an inspected `Concept` with direct attribute/key
getters and properties; `get_relationship(name=...)` returns a typed relationship
snapshot and `get_unit(name=...)` returns `Definition[UnitDefinition]`. ID lookup uses
`concept_id`, `relationship_id` or `unit_id`, with exactly one selector. Dependency namespaces remain separate.
`DomainModelBundle.get_concept()` uses the same exact name/ID selectors synchronously
against that bundle's local active or removed definitions, returning `Concept` without
I/O, audit writes or a `revision` argument. Missing/wrong-kind entries use the existing
`DefinitionNotFoundError`/`DefinitionKindMismatchError`; it never searches dependencies
or current model state. Removed definitions remain inspectable but cannot be projection roots.
Definition body kinds use `DefinitionKind` string-enum members; callers need no
kind assertions. Attributes and keys use the same naming inputs and generated IDs within their owning definition.

Rejecting a never-approved creation releases its pending name reservation; its ID
and proposal remain in history. Approved/removed definition names stay reserved.

## 1. Configure once

`Client()` (or `config=None`) loads `domain-kernel.toml` from the captured process
working directory, using fresh defaults only when the file is absent. It never
searches a Git root, parent directories or global configuration. An invalid,
unreadable or non-file path raises `ConfigurationError` without fallback.
`Client(config="config/production.toml")` selects that exact file strictly; `Path`
inputs are also supported. `Client(config=ClientConfiguration())` explicitly uses
built-in defaults; any configuration object bypasses file discovery and merging.
Configuration is loaded and captured once; later file or working-directory changes
do not reconfigure the client or rebase paths. Construction does not initialize
schema. When `database` is omitted, the first awaited database operation initializes
default SQLite and waits for success. Explicit database settings and injected
transaction providers retain operator setup. Existing incompatible/partial schemas
and initialization failures stop the operation; no migration, reset or fallback.
Model inference is optional;
`gateway` is a caller-owned `ModelGateway`, or `None` for manual-only use. Set
`ClientConfiguration.model_gateway` before creating the client; reuse its handles
for discovery. Gateway presence does not invoke inference during manual operations.
Every `ClientConfiguration` field has a default; the architecture shows [minimal startup
and capability-specific overrides](ARCHITECTURE.md#configure-the-sdk-in-python).
This local example overrides only input locations, the reference-pack catalog and
optional gateway. No `.env` file is needed; set `env_file` only when selecting one.

`parsed_source_resolver` is a caller-owned `ParsedSourceResolver`, or `None` when
host-parsed evidence is not needed. Register it once here to follow section 6 with
the same client/project/model; creating the integration does not retrieve content.

```python
from domain_kernel import Client, ClientConfiguration, ClientIntegrations, ParsedSourceProvider
from domain_kernel.configuration import (
    FilesystemReader,
    ReferencePackCatalog,
)

# Configure the client once; the TOML startup alternative is shown below.
local_inputs = FilesystemReader(name="inputs", root="./data")
references = FilesystemReader(name="references", root="./reference-packs")
configuration = ClientConfiguration(
    model_gateway=gateway,
    readers=[local_inputs, references],
    reference_packs=ReferencePackCatalog(reader=references),
)

integrations = (
    ClientIntegrations(
        parsed_source_providers=[
            ParsedSourceProvider(name="content-platform", resolver=parsed_source_resolver),
        ],
    )
    if parsed_source_resolver is not None
    else None
)
client = Client(config=configuration, integrations=integrations)

# A project is a technical namespace for sources/models, not a delivery engagement.
project = await client.create_project(actor="user:model-editor", display_name="Example Co")
project = await client.get_project(name="example-co")
page = await client.list_projects(limit=50, cursor=None)
next_page = (
    await client.list_projects(limit=50, cursor=page.next_cursor) if page.next_cursor else None
)
```

Defaults: SQLite at `.domain-kernel/state.sqlite3`, `inputs` rooted at `.`, and
`artifacts` at `.domain-kernel/artifacts`; this example replaces the default reader
list explicitly. Processing and source-selection limits use their bounded defaults.
Parser defaults resolve on use and require the relevant installed extras; no
originals, extracted text or evidence excerpts are retained automatically.
No public open/close cycle is required: SDK-owned resources are operation-scoped,
with cleanup on success/failure/cancellation; injected resources remain caller-owned.
No client-owned pool or background task may require an undisclosed shutdown step.
Models default to `reference_pack=None`: author and discover from company knowledge
without a placeholder pack. A selected `ReferencePack` adds reusable business
knowledge, patterns and declared checks. Core integrity/evidence/review rules apply
in either case. This replaces the earlier proposed `Profile` terminology/API;
source profiling and AWS credentials profiles keep their separate meanings.
The caller owns injected gateways, transports, and pools. Configuration snapshots copy settings but retain the exact gateway instance; existing handles cannot swap it after startup.

```python
configuration_report = client.inspect_configuration()
configuration_report  # Captured origin, resolved paths, setup mode and redacted summaries.
```

This synchronous report performs no I/O or health probes and exposes no credentials,
DSNs or provider objects. It describes configured adapters, not their availability.
Explicitness of `database` survives default normalization and TOML loading, so even
explicit `SQLite()` selects operator setup; an injected transaction factory always
owns setup. See [database initialization](ARCHITECTURE.md#database-initialization).

### Remote inputs, independent output storage, and credentials

```python
from domain_kernel.configuration import (
    AwsDefaultChain,
    AwsProfile,
    DoclingParser,
    EntraClientSecret,
    Env,
    OpenpyxlParser,
    Parsers,
    PostgreSQL,
    ReferencePackCatalog,
    S3Reader,
    S3Store,
    SharePointReader,
    Storage,
)

sharepoint_credentials = EntraClientSecret(
    tenant_id=Env(env="DK_SHAREPOINT_TENANT_ID"),
    client_id=Env(env="DK_SHAREPOINT_CLIENT_ID"),
    client_secret=Env(env="DK_SHAREPOINT_CLIENT_SECRET"),
)

input_reader = S3Reader(
    name="inputs",
    bucket="client-inputs",
    prefix="inputs/",
    region="eu-central-1",
    credentials=AwsProfile(profile="client-inputs"),
)

manual_reader = SharePointReader(
    name="manuals",
    drive_id="replace-with-drive-id",
    root_item_id="replace-with-folder-item-id",
    credentials=sharepoint_credentials,
)

artifact_store = S3Store(
    name="artifacts",
    bucket="approved-outputs",
    prefix="artifacts/",
    region="eu-central-1",
    credentials=AwsDefaultChain(),
)

remote = ClientConfiguration(
    env_file=".env",  # Omit in production when using runtime environment values.
    database=PostgreSQL(dsn=Env(env="DK_DATABASE_DSN")),  # Optional adapter.
    readers=[input_reader, manual_reader, references],
    reference_packs=ReferencePackCatalog(reader=references),
    parsers=Parsers(excel=OpenpyxlParser(), documents=DoclingParser()),
    storage=Storage(artifact_store=artifact_store),
)
```

Python composes typed objects directly. Credential fields accept provider-specific
types: AWS for S3, supported Entra configurations for SharePoint. Names are stable
labels for serialized source/job references; duplicate reader/store names fail.

### Complete `domain-kernel.toml`

Save this as `domain-kernel.toml`: PostgreSQL state, S3 inputs/outputs, and
SharePoint manuals. Replace provider locations and supply the referenced secrets.

```toml
schema_version = 1
env_file = ".env"  # Explicit local file; omit for environment-only deployments.

[database]
type = "postgresql"
dsn = { env = "DK_DATABASE_DSN" }

[credentials.input_aws]
provider = "aws_profile"
profile = "client-inputs"

[credentials.output_aws]
provider = "aws_default_chain"

[credentials.sharepoint]
provider = "entra_client_secret"
tenant_id = { env = "DK_SHAREPOINT_TENANT_ID" }
client_id = { env = "DK_SHAREPOINT_CLIENT_ID" }
client_secret = { env = "DK_SHAREPOINT_CLIENT_SECRET" }

[readers.inputs]
type = "s3"
bucket = "client-inputs"
prefix = "inputs/"
region = "eu-central-1"
credentials = "input_aws"

[readers.manuals]
type = "sharepoint"
drive_id = "replace-with-drive-id"
root_item_id = "replace-with-folder-item-id"
credentials = "sharepoint"

[readers.references]
type = "filesystem"
root = "./reference-packs"

[reference_packs]
reader = "references"  # Resolves to this approved typed reader; no public fallback.

[parsers.excel]
type = "openpyxl"

[parsers.documents]
type = "docling"

[stores.artifacts]
type = "s3"
bucket = "approved-outputs"
prefix = "artifacts/"
region = "eu-central-1"
credentials = "output_aws"

[storage]
artifact_store = "artifacts"

[processing]
mode = "memory"
max_source_bytes = 67108864  # 64 MiB.
max_concurrent_sources = 2
max_expanded_bytes = 268435456
max_pages = 1000

[source_selection]
max_files = 1000
max_listing_entries = 10000
max_listing_depth = 32
listing_timeout_seconds = 60

[retention]
originals = false
extracted_text = false
evidence_excerpts = false

[inference]
timeout_seconds = 60.0
max_attempts = 3

[publication]
allow_reviewed_nonblocking_questions = true
```

The loader resolves TOML's named credentials/stores/reference pack reader into typed objects;
missing or incompatible references fail closed. Python needs no credential registry.
Secrets remain references; the host-owned gateway retains its provider/model configuration.
Choose this startup alternative to combine the TOML settings with that live instance:

```python
configuration = ClientConfiguration.from_toml(
    model_gateway=gateway,
)
client = Client(config=configuration, integrations=integrations)
```

`from_toml()` defaults to `path="domain-kernel.toml"`; provide `path` for another
location. It requires the file even when the path is omitted: missing, unreadable
or invalid files raise `ConfigurationError`. It parses and validates settings,
normalizes named bindings and retains the file directory as `base_dir`; `Client`
resolves Env references afterward. With no gateway, `Client()` discovers the
conventional file, or `Client(config="config/production.toml")` loads an explicit
path strictly. File/JSON input
rejects the runtime `model_gateway` key, even null; only a Python argument supplies it.
The field defaults to `None`, is omitted from dumps/generated schemas/repr/diagnostics,
and is never copied, constructed or closed by the SDK. Ordinary settings remain strict;
no provider registry, serialized callable or gateway replacement is introduced.
Each selected adapter requires its optional runtime extra.

Only referenced variables resolve: process environment → selected `.env` → error.
There is no automatic `.env` loading, parent-directory search, interpolation, or
mutation of `os.environ`. Relative configuration-file paths use the captured working
directory; paths inside TOML use its directory. Python paths use `base_dir`
(captured working directory by default).
AWS chains use their native sources; `.env` keys require explicit `AwsStatic`.
A reference pack catalog may use any configured approved reader. Without one,
`await client.list_reference_packs()` returns an empty page and `await client.get_reference_pack(...)` raises
`ReferencePackNotFoundError`. Models and standalone pack composition/loading remain
usable. Unknown packs never trigger public downloads.

### Pydantic validation: fail closed

```python
from domain_kernel import ConfigurationError
from domain_kernel.configuration import (
    InMemoryProcessing,
)
from pydantic import ValidationError

# ClientConfiguration and nested settings are typed Pydantic models; the runtime gateway is omitted.
schema = ClientConfiguration.model_json_schema()

try:
    InMemoryProcessing(max_source_bytes=0)  # Also rejects "1024", True, typos.
except ValidationError:
    pass  # Correct the input; invalid values never become defaults.

try:
    client = Client(config="domain-kernel.toml")
except ConfigurationError as error:
    error.issues  # Sanitized field paths/codes; no secret values or raw input.
    raise
```

Pydantic Settings loads controlled sources into private runtime settings. Require
strict types/bounds, forbidden extra fields, validated defaults, tagged adapter
unions, valid cross-references, and revalidated independent client snapshots.
No adapter creation precedes validation; remote authentication fails on use.
A missing gateway raises `MissingCapabilityError` only when inference is requested.
Resolved secrets stay private and redacted, including exception chains.

## 2. Consume a bundle independently

No Client, configuration, database, readers, gateway or optional adapters are needed.
File/transport I/O belongs to the caller. `bundle.serialize()` returns canonical UTF-8
JSON bytes; `DomainModelBundle.deserialize(payload=...)` accepts bytes or text and
returns a validated immutable bundle. Both methods use the same built-in codec without
audit writes or actor attribution. Invalid content raises `InvalidBundleError`; unknown
wire versions raise `UnsupportedBundleVersionError`. Deserialization never fetches evidence.

```python
from pathlib import Path

from domain_kernel import DomainModelBundle

bundle_path = Path("domain-model.bundle.json")
payload = bundle_path.read_bytes()  # Host-owned I/O.
loaded = DomainModelBundle.deserialize(payload=payload)

print(f"Model version: {loaded.version}")
print(f"Model kind: {loaded.kind.value}")

for definition in loaded.content.definitions:
    print(f"{definition.display_name} ({definition.name}): {definition.meaning}")

for question in loaded.publication.nonblocking_questions:
    print(f"Nonblocking question: {question.text}")

# Additional provenance and historical content are available on the same snapshot.
# Inspect loaded.scope, loaded.model_version and loaded.content.retired_definitions.
loaded.content.source_alignments
loaded.publication.candidate.proposals
# Inspect loaded.content.reference_dispositions and loaded.publication.reference_pack.
# Inspect loaded.publication.candidate.decisions and loaded.approval.
canonical_bytes = loaded.serialize()
# Select this bundle's format version, independently of its model release version.
wire_schema = DomainModelBundle.get_json_schema(schema_version=loaded.schema_version)
# DomainModelBundle.deserialize(payload=payload, expected_hash=transport_hash) verifies transport bytes.
```

`DomainModelBundle.get_json_schema()` returns closed JSON Schema text for the complete
bundle format through the built-in codec. The synchronous class method needs no bundle
instance, Client, configuration, optional adapter or I/O and creates no audit records.
Its optional `schema_version` defaults to the current supported format, `"1.0"`;
unsupported versions raise `UnsupportedBundleVersionError` without fallback or retrieval.
It describes bundle wire structure, not a published model release or a business-data
projection. There is no standalone bundle-schema function in the public API.

The version-1.0 wire contract mirrors the annotated bundle and nested records in
[INTERFACES.md](INTERFACES.md): explicit `format`/`schema_version`, tagged union
members, explicit nulls and array representations for tuples. All wire fields are
required; unknown fields/tags, duplicate keys, invalid hashes and unregistered
versions fail closed. Strict decoding preserves typed values and stable identities.
Attribute records explicitly encode `required`, `collection`, `min_items` and
`max_items`; these fields participate in hashes. Single values have null item bounds;
collections have a resolved integer minimum and integer-or-null maximum. Legacy
attribute shape fields are rejected, without inferred presence or silent migration.
Enums and nominal IDs encode as strings. `DecisionValue` is the explicit field-mapping
exception: native Python `value` becomes `{data_type, lexical_value}` on the wire.
Its decoder returns the exact supported native scalar; no null outputs or floats.
Absent packs encode as `null` consistently in candidate, publication and validation;
active reference alignments/dispositions must then be empty. Historical pack audits
remain available, and the core semantic-mapping version remains explicit.

Canonical output uses sorted keys, UTF-8, no insignificant whitespace, preserved
array order and UTC timestamps with six fractional digits. Exact decimal values
use typed canonical lexical strings. Candidate/bundle hashes exclude their own
root hash field; reference pack hashes exclude `pin.content_hash`. Original transport
hashes remain distinct. No silent migration or lossy semantic projection is allowed.
Breaking schema changes require a new major; additions need a registered minor
schema/codec. Initially only 1.0 is supported. Structural loading checks internal
references and approval bindings; it does not reauthenticate actors, re-run optional
semantic validators, or establish the current availability/truth of external evidence.
Qualified references resolve against `loaded.publication.candidate.dependency_bundles`,
which materialize the exact declared dependency pins recursively. Loading verifies
scope, revisions and hashes; it rejects cycles, conflicting pins and nesting beyond
16 dependency edges. `max_bytes` bounds the entire payload. Baseline pins are
historical provenance and do not trigger loading or embedding the baseline bundle.

## 3. Construct a model without inference

Omit `reference_pack` unless you want to select one. Kind remains explicit through
`ModelKind`: it records whether content describes observations or proposals;
publication preserves that kind. No pack is inherited implicitly from a baseline.

```python
from domain_kernel import RelationshipCardinality, DataType, DefinitionStatus, ModelKind

from domain_kernel import (
    Accept,
    AttributeDefinition,
    ScalarValueType,
    ConceptDefinition,
    DomainModelBuilder,
)

model = await project.create_model(
    actor="user:model-editor",
    display_name="Component Catalog",
    description="Component types, suppliers and inventory terms for purchasing and manufacturing.",
    kind=ModelKind.PROPOSED,
)
model = await project.get_model(name="component-catalog")
models = await project.list_models(limit=50, cursor=None)
# Inspect model.info and model.scope.

component_case = await model.propose_definition(
    actor="user:model-editor",
    display_name="Component",
    meaning="A purchased or manufactured item used in an assembly.",
    body=ConceptDefinition(
        attributes=[
            AttributeDefinition(
                display_name="number",
                value_type=ScalarValueType(data_type=DataType.STRING),
                required=True,
            ),
        ]
    ),
    aliases=["Part"],
    reason="Explicit caller-supplied definition.",
)
component_id = component_case.definitions[0].id
receipt = await model.decide_review(
    case=component_case,
    decision=Accept(reason="Accept this exact local definition."),
    actor="user:model-editor",
)

# Reload after accepting the component, then inspect it for the new plan.
model = await project.get_model(name=model.info.name)
component = await model.get_concept(name="component")
builder = DomainModelBuilder(model_info=model.info)

supplier_id = builder.add_concept(
    display_name="Supplier",
    meaning="An organization providing components.",
    attributes=[
        AttributeDefinition.string(
            display_name="Supplier Number",
            required=True,
        ),
    ],
)
builder.add_relationship(
    display_name="Supplies",
    meaning="A supplier provides a component.",
    source=supplier_id,
    target=component,
    # Each supplier can supply many components, and vice versa.
    cardinality=RelationshipCardinality.many_to_many(),
)
plan = builder.build_change_plan(
    reason="Define suppliers and how they supply existing component types.",
)
change_case = await model.propose_change_plan(
    actor="user:model-editor",
    plan=plan,
)

# Preview both additions before explicitly accepting them together.
decision = Accept(reason="Reviewed the supplier definition and its relationship to Component.")
impact = await model.preview_changes(case=change_case, decision=decision)
# Inspect change_case.members, impact.definition_changes and impact.blockers.
# After the reviewer inspects the members and combined effect:
await model.decide_review(
    case=change_case,
    decision=decision,
    actor="user:model-editor",
)

definition = await model.get_definition(definition_id=component_id)
revision = await model.get_definition(definition_id=component_id, revision=definition.revision)
definitions = await model.list_definitions(status=DefinitionStatus.APPROVED, limit=50)
history = await model.get_definition_history(definition_id=component_id, limit=50)
```

With no pack, acceptance approves the definition without creating a reference
disposition. Selecting a pack requires explicit reference mappings/extensions;
source-to-model reconciliation applies in both cases. Manually supplied content keeps
its evidence basis and rationale; acceptance does not convert hypotheses into facts.
Host applications establish actor identity, authority and decision-routing policy.

The supplier plan combines a generated concept ID with an inspected existing concept;
submission does not accept either addition. `AttributeDefinition.string(required=True)`
requires field presence, while a separate key declares business identifier uniqueness.

Review impact exposes `definition_changes`, `source_alignment_changes`,
`reference_disposition_changes` and `compatibility` as read-only views of its existing
`ChangeSet`, without new wire fields. The full `impact.changes` remains available for
comparison metadata. Use `model.preview_changes()` and separate `model.decide_review()`
for public review operations; case-local effect helpers are private.

### Author and correct with one builder

For connected definitions, use the pure `DomainModelBuilder` instead of manually creating and
then grouping each leaf case. This optional branch creates a separate model:

```python
from domain_kernel import Accept, RelationshipCardinality, DomainModelBuilder, ModelKind

builder_model = await project.create_model(
    actor="user:model-editor",
    display_name="Builder Catalog",
    description="Inventory catalog types, physical units and the relationships between them.",
    kind=ModelKind.PROPOSED,
)
authoring = DomainModelBuilder(model_info=builder_model.info)
item_type_id = authoring.add_concept(
    display_name="Item Type", meaning="A catalog-level item description."
)
unit_id = authoring.add_concept(
    display_name="Physical Unit", meaning="An individual physical instance."
)
authoring.add_relationship(
    display_name="Has Type",
    meaning="A physical unit belongs to an item type.",
    source=unit_id,
    target=item_type_id,
    # Many physical units can share the same item type.
    cardinality=RelationshipCardinality.many_to_one(),
)
plan = authoring.build_change_plan(reason="Model catalog types and physical units explicitly.")
plan.operations  # Inspect the immutable, typed intent; nothing has been persisted yet.
case = await builder_model.propose_change_plan(actor="user:model-editor", plan=plan)
accept = Accept(reason="Reviewed every definition and relationship in this plan.")
impact = await builder_model.preview_changes(case=case, decision=accept)
case.proposed_changes
case.definitions
impact.definition_changes
impact.compatibility
impact.blockers
# After the reviewer inspects the members and combined effect:
receipt = await builder_model.decide_review(case=case, decision=accept, actor="user:model-editor")
```

`add_concept` accepts typed attributes; `add_definition(body=...)` accepts any existing supported
definition body. Pass inspected definitions directly to relationship endpoints and
other typed reference parameters; their snapshots are recorded automatically. For
IDs embedded in raw bodies/attributes, supply `referenced_definitions` in the same call.
Published dependency references remain qualified. The builder
never fetches a definition or a pack, invokes inference, writes state or approves content.
New IDs are provisional until proposal submission reserves them. Build validates
local structure; submission/acceptance validate current repository state.

Before a new builder session on an existing model, reload it through its owning
`project` with `await project.get_model(name=model.info.name)`. Its `.info` property
is a loaded snapshot, not a hidden database query; newly created models need no
extra reload. Further concurrent changes still make the plan stale. Re-inspect and
rebuild instead of rewriting its expected revision; retries reuse the original plan.
`Has Type` (lookup name `has-type`) is a business relationship from physical unit
to item type: many units can share one type. It is separate from reviewing whether
one definition's meaning is `narrower_than()` another's.

For a revision, pass the inspected definition and changed fields directly. This builder path
preserves untouched content; lower-level `propose_revision` remains full replacement.

```python
from domain_kernel import DomainModelBuilder

builder_model = await project.get_model(name=builder_model.info.name)
item_type = await builder_model.get_concept(name="item-type")
physical_unit = await builder_model.get_concept(name="physical-unit")
has_type = await builder_model.get_relationship(name="has-type")
builder = DomainModelBuilder(model_info=builder_model.info)
builder.edit_concept(
    concept=item_type,
    display_name="Catalog Item Type",
    meaning="A reusable catalog definition shared by individual physical units.",
    aliases=["Item Type"],
)
builder.edit_relationship(
    relationship=has_type,
    display_name="Has Item Type",
    source=physical_unit,
    target=item_type,
)
revision_plan = builder.build_change_plan(
    reason="Clarify the type definition without losing evidence."
)
revision_case = await builder_model.propose_change_plan(
    actor="user:model-editor", plan=revision_plan
)
# Preview and decide revision_case explicitly through the same review APIs.
```

For a coordinated correction, the following separate branch assumes the application
has inspected `original_case` and chosen a nonempty `selected_occurrences` sequence
in `model`. Only those selected mappings will be replaced;
retirement or dependent edits must be explicitly added when intended.

```python
from domain_kernel import DomainModelBuilder, MapToPlannedDefinition

model = await project.get_model(name=model.info.name)
inspected_model = model.info
corrections = DomainModelBuilder(model_info=inspected_model)
new_unit_id = corrections.add_concept(
    display_name="Physical Unit", meaning="One physical instance rather than a catalog type."
)
corrections.correct_mapping(
    case=original_case,
    proposal_ids=selected_occurrences,
    decision=MapToPlannedDefinition(
        definition_id=new_unit_id, reason="These inspected occurrences describe physical units."
    ),
)
combined_plan = corrections.build_change_plan(reason="Correct these selected interpretations.")
combined_case = await model.propose_change_plan(actor="user:model-editor", plan=combined_plan)
# MapToPlannedDefinition becomes MapToDefinition with the validated final snapshot.
# The returned parent exposes every member/action for preview and explicit acceptance.
```

`edit_concept`/`edit_relationship`, `remove_concept`/`remove_relationship` and
`restore_concept`/`restore_relationship` operate on inspected objects and return `None`.
Generic definition methods cover other bodies. `correct_mapping`, `include_case`
and `add_change_plan` preserve explicit review intent. Omitted edit fields retain
their values; explicit empty collections replace them. New references retain inspected snapshots; unchanged references
in an inspected definition retain their workspace guard. No untyped patches or
inferred merge/split targets are accepted. Included pending cases require an explicit
action; question/confirmation/pack-change cases remain separate.

`build_change_plan(reason=...)` freezes a detached plan; `reason` explains why the
changes are proposed and supplies the reason for newly authored operations. Included
plans and review actions retain their own reasons. Rebuilding unchanged content with
the same reason returns the same ID; editing or changing the reason creates a new plan.
`propose_plan` uses that ID as its default idempotency key:
retries replay the same parent, while changed payload under the same identity conflicts.
Plan ID independently binds the payload/parent even with a caller-supplied retry key;
changing that key cannot reuse the plan ID for different intent. Concurrent identical
submissions converge on one parent with no duplicate or partial member cases.
Submission atomically creates/reserves all members and the parent, with one workspace
advance and a guard for the resulting revision. Any failure leaves no partial cases.
Staleness never triggers an automatic rebase; inspect current state and build again.

Preview and decide take the inspected `case` directly, carrying its ID, scope and
version; callers do not repeat `case_id` or `expected_version`. Preview is read-only;
decision application rechecks stored state atomically and never substitutes a newer
case. An attributed `Accept` applies all effects together.

Parent `Reject` atomically rejects all proposals generated by that plan, including
new correction cases, and releases pre-existing included cases as pending with new
versions. The parent records `generated_member_case_ids`; provenance survives plan
merging and persistence. Only generated members receive child rejection decisions.
Rejecting a correction leaves its prior effective decision intact. Never-approved
creations release pending name reservations, retaining their IDs and audit history.
Submit a fresh plan for revised work; replaying the rejected plan returns that same parent.
Publication still requires preparation/validation/publication. Plans and member decisions
remain in the audit, without executing aggregate effects twice.

### Edit attributes and keys

This independent recipe assumes `model` contains an approved `manufacturer` concept
with `manufacturer-code` and `legacy-code` attributes and matching
`manufacturer-identity` and `legacy-identity` keys. Complete any pending review first.

```python
from domain_kernel import AttributeDefinition, DomainModelBuilder, KeyDefinition

model = await project.get_model(name=model.info.name)
manufacturer = await model.get_concept(name="manufacturer")
attributes = manufacturer.attributes
keys = manufacturer.keys
manufacturer_code = manufacturer.get_attribute(name="manufacturer-code")
legacy_code = manufacturer.get_attribute(name="legacy-code")
manufacturer_identity = manufacturer.get_key(name="manufacturer-identity")
legacy_identity = manufacturer.get_key(name="legacy-identity")

# Alternative exact lookups within the same inspected snapshot.
same_attribute = manufacturer.get_attribute(attribute_id=manufacturer_code.id)
same_key = manufacturer.get_key(key_id=manufacturer_identity.id)

builder = DomainModelBuilder(model_info=model.info)
country_code = AttributeDefinition.string(
    display_name="Country code",
    required=True,
)
builder.add_attribute(concept=manufacturer, attribute=country_code)
erp_code = AttributeDefinition.string(
    display_name="ERP manufacturer code",
    name="erp-code",
    required=True,
)
builder.add_attribute(concept=manufacturer, attribute=erp_code)

builder.edit_attribute(
    concept=manufacturer,
    attribute=manufacturer_code,
    display_name="Manufacturer registration code",
)
builder.edit_key(
    concept=manufacturer,
    key=manufacturer_identity,
    display_name="Manufacturer identity by country",
    attributes=[country_code.id, manufacturer_code.id],
)
erp_identity = KeyDefinition(
    display_name="ERP manufacturer identity",
    name="erp-identity",
    attributes=[erp_code.id],
)
builder.add_key(concept=manufacturer, key=erp_identity)
builder.remove_key(concept=manufacturer, key=legacy_identity)
builder.remove_attribute(concept=manufacturer, attribute=legacy_code)

plan = builder.build_change_plan(
    reason="Scope registration codes by country, add ERP identity and remove legacy identifiers."
)

case = await model.propose_change_plan(
    actor="user:model-editor",
    plan=plan,
)
# Preview and explicitly accept; retrieve the concept again to inspect the new revision.
```

Getters accept exactly one name or ID, read only the inspected revision and raise
`AttributeNotFoundError`/`KeyNotFoundError` when missing. Attribute names are unique
within their owning definition; key names within its keys. Duplicate attachment
raises `AttributeAlreadyExistsError`/`KeyAlreadyExistsError`, without suffixes.
IDs are generated once by construction and preserved by attachment, edits and codecs.

`edit_attribute` accepts `display_name`, `value_type`, `required`, `collection`,
`min_items`, `max_items`, `nullability`, `constraints` and `terminology`; `edit_key` accepts `display_name` and `attributes`.
Omission preserves values, supplied collections replace them, and neither method
changes the ID or stable name. `min_items=None` resets a collection minimum to zero;
`max_items=None` removes its upper bound. Switching to `SINGLE` requires explicitly
clearing stored item bounds; switching from `SINGLE` resolves inherited `None` bounds
to zero/unbounded. Validate the final shape; omitted `required` is preserved.
Adds return the supplied record's ID; edits/removals return `None`. For new concepts, pass these records directly in
`add_concept(attributes=[...], keys=[...])`. Introduced reference-valued fields use
`referenced_definitions=[inspected_target]` on add/edit calls when their value type
contains an existing bare ID, following the same inspected-binding contract.

Distinct child edits coalesce into one reviewed concept revision. Whole-collection
replacement conflicts with child operations on that collection; disjoint concept
metadata edits are allowed. Validate the final graph and explicitly repair/remove
dependent keys or other references. Removing children preserves prior concept
revisions and published bundles; it never alters host instance data.

### Revise an approved definition

A revision proposal supplies the complete replacement content for the same identity.
Preserve aliases and evidence explicitly when they still apply. The old revision
remains available and no active change occurs until the case is accepted.

```python
component = await model.get_definition(definition_id=component_id)
revision_case = await model.propose_definition_revision(
    actor="user:model-editor",
    definition_id=component.id,
    expected_revision=component.revision,
    display_name=component.display_name,
    meaning="A catalog item type purchased or manufactured for use in an assembly.",
    body=component.body,
    aliases=component.aliases,
    evidence=component.evidence,
    reason="Clarify that the existing concept describes item types, not individual units.",
)
revision_decision = Accept(reason="Reviewed the clarified meaning and its dependent effects.")
impact = await model.preview_changes(case=revision_case, decision=revision_decision)
# Inspect impact.definition_changes, impact.invalidated_decision_ids and impact.blockers.
# After the user has inspected this impact:
await model.decide_review(
    case=revision_case,
    decision=revision_decision,
    actor="user:model-editor",
)
```

The revision is checked both when proposing and when applying a change. `Reject`
can cancel an obsolete pending proposal using the current case version without
requiring its old target revision or applying any target change. Any underlying
required alignment, confirmation or reference pack gap remains blocking. `EditDefinition`
can revise proposed content on a compatible pending case, but cannot directly
mutate an arbitrary approved definition. A change in the actual identity requires
new definitions and explicit replacement lineage, rather than repurposing an ID.

This optional removal branch opens a case for an inspected active concept;
it is not part of the continuing catalog example. Here `retiring_id` and
`replacement_ids` are chosen by the caller; an empty list means no replacement.

```python
model = await project.get_model(name=model.info.name)
retiring = await model.get_concept(concept_id=retiring_id)
replacements = [
    await model.get_concept(concept_id=replacement_id) for replacement_id in replacement_ids
]
builder = DomainModelBuilder(model_info=model.info)
builder.remove_concept(concept=retiring, replacements=replacements)
retirement_plan = builder.build_change_plan(
    reason="Remove this meaning after reviewing its replacements and dependencies."
)

retirement_case = await model.propose_change_plan(
    actor="user:model-editor",
    plan=retirement_plan,
)
retirement_impact = await model.preview_changes(
    case=retirement_case, decision=Accept(reason="Approve this explicit retirement.")
)
retirement_impact
# Submit Accept through decide_review only after inspecting this proposed change.
```

Acceptance appends a retired revision; consumers find its tombstone in
`content.retired_definitions`, separate from active `content.definitions`.
Replacements must be active local definitions at decision time. Historical lineage
can point to later-retired definitions, remains acyclic and never redirects references
automatically. Active references to retired definitions block publication. A merge
or split is an explicit sequence of definition proposals, selected mapping corrections,
dependent revisions and retirements. Each decision is atomic; intermediate workspace
states may have blockers. History and existing published versions remain unchanged.

A mistaken retirement is reversible through an explicit restoration proposal:

```python
model = await project.get_model(name=model.info.name)
retired = await model.get_concept(concept_id=retiring_id)
builder = DomainModelBuilder(model_info=model.info)
builder.restore_concept(concept=retired)
restoration_plan = builder.build_change_plan(reason="Restore this meaning after review.")

restoration_case = await model.propose_change_plan(
    actor="user:model-editor",
    plan=restoration_plan,
)
```

Preview and accept the returned case through the same review APIs. Acceptance appends an approved revision under the same ID using
the last retired content, clears replacement IDs on that active revision and preserves
retirement history. Prior mappings/confirmations are not automatically restored;
references and obligations are revalidated. Make further edits with a revision proposal.

### Review coordinated edits atomically

This optional branch constructs two definitions and their relationship as one
reviewable change. For a split/merge, use the same mechanism with inspected source
correction, dependent-revision and retirement cases as additional members.

```python
from domain_kernel import RelationshipCardinality

from domain_kernel import CaseDecision

new_cases = [
    await model.propose_definition(
        actor="user:model-editor",
        display_name="Item Type",
        meaning="A catalog-level description of an item.",
        body=ConceptDefinition(),
        reason="Propose the distinct inventory meanings together.",
    ),
    await model.propose_definition(
        actor="user:model-editor",
        display_name="Physical Unit",
        meaning="An individual physical instance of an item type.",
        body=ConceptDefinition(),
        reason="Propose the distinct inventory meanings together.",
    ),
]
unit_type_case = await model.propose_definition(
    actor="user:model-editor",
    display_name="Has Type",
    meaning="A physical unit belongs to an item type.",
    body=RelationshipDefinition(
        source_concept_id=new_cases[1].definitions[0].id,
        target_concept_id=new_cases[0].definitions[0].id,
        cardinality=RelationshipCardinality.many_to_one(),
    ),
    reason="Link the two proposed definitions using their reserved local IDs.",
)
change_case = await model.propose_change_set(
    actor="user:model-editor",
    decisions=[
        CaseDecision(
            case_id=new_cases[0].id,
            expected_version=new_cases[0].version,
            decision=Accept(reason="Include the item-type proposal."),
        ),
        CaseDecision(
            case_id=new_cases[1].id,
            expected_version=new_cases[1].version,
            decision=Accept(reason="Include the physical-unit proposal."),
        ),
        CaseDecision(
            case_id=unit_type_case.id,
            expected_version=unit_type_case.version,
            decision=Accept(reason="Include their proposed relationship."),
        ),
    ],
    expected_workspace_revision=model.info.revision,
    reason="Review the complete connected definition graph together.",
)
accept_group = Accept(reason="Reviewed every member and the combined impact.")
group_impact = await model.preview_changes(case=change_case, decision=accept_group)
# Inspect group_impact.definition_changes, group_impact.blockers and change_case.members.
# Only after inspecting all members and their combined impact:
group_receipt = await model.decide_review(
    case=change_case,
    decision=accept_group,
    actor="user:model-editor",
)
group_receipt.member_decision_ids
```

Members must be pending content/alignment leaf cases in one model. Their actions are
explicit; no automatic acceptance of discovered work. Proposal creation reserves
members and advances their versions; the returned parent contains those reserved
versions and a guard for the post-creation workspace revision. Members cannot be
decided or reserved elsewhere while grouped. New workspace edits make the group stale.

Preview/accept evaluate one prospective graph, so references to definitions created
or restored in the same group are valid. Contradictory writes, duplicate effects,
nested groups and unresolved references introduced by the affected edits fail.
Questions, confirmations and pack changes remain separate cases; grouping fails
while a pack-change case is pending. Unrelated existing
publication blockers do not prevent a valid coordinated edit.

Parent `Accept` commits every member effect and linked decision record together,
advances the workspace once, and creates required dependent review. Any failure
rolls back the entire acceptance. This `propose_change_set()` example groups only
pre-existing cases: parent `Reject` releases them as pending with new versions,
without applying their actions or recording child rejections. Use the current
inspected parent case even when its workspace/target guards are obsolete. For a
builder-created plan, generated members are instead rejected with the parent;
only pre-existing included cases are released. Rejection/release is atomic.
Reload them before regrouping or cancelling obsolete proposals. Later corrections
address exact member decisions; audit readers must not replay both the aggregate
and each member's effects. `DecisionRecord.applied_changes` records the committed
change; generated-member provenance and `released_case_ids` survive portable decision
snapshots, while parent/member links distinguish actual decisions from releases.

### Optional retry keys

Where exposed, `idempotency_key=None` generates a fresh internal invocation key once
per call, reused for internal retries/checkpoints without mutating caller inputs.
It is not derived from document hashes or request content; another unkeyed discovery
call can start a new run over the same evidence. Name/version/review guards and immutable
artifact identity/reuse still apply independently of invocation keys.
For retries across calls or workers, supply a host request/job ID retained before the
first attempt; reuse it with the same actor and request. Basic examples omit keys;
recovery examples below retain them. Known discovery runs can be retrieved or resumed
when eligible using their run ID. Plan-ID defaults and recorded manifest-child keys
remain stable; unkeyed folder selections capture new manifests.

### Durable action attribution

All durable SDK business actions require `actor=...`, including creation, ingestion,
profiling/copying, discovery/reconciliation, proposal submission, review, saved
compilation/validation, preparation, publication and export. Hosts verify user/service
identities; nested work inherits attribution and parent links. Local builders, previews,
reads and pure conversions have no persistent audit side effect. Derivative retention
occurs in attributed ingestion/profile/discovery work, not a read method.

Append-only records preserve action/outcome, actor, SDK time, applicable reason and exact
before/after resources. Plans group changes; existing member decisions and definition
revisions retain per-definition detail. The submitter and reviewer are distinct roles.
State, audit and idempotency outcome commit together. Matching keyed retries (or the
documented identity-based defaults) do not duplicate history; changed actors conflict under the same key or submitted plan ID. Blocked
preparations retain their diagnostics and audit before raising. Persisted run failures
retain their actual outcome; failed uncommitted work creates no success record.

Copy/export writes persist an attributed intent before external I/O and an outcome after
verification, with recovery for uncertain writes. They do not claim cross-store atomicity.
Broader project audit stays in producer storage; bundle provenance and authorization
remain portable. See [the audit contract](ARCHITECTURE.md#durable-action-audit).

```python
project_history = await project.get_audit_history(limit=50)
model_history = await model.get_audit_history(limit=50)
# Follow next_cursor to inspect subsequent pages.
```

## 4. Compile, validate, prepare and publish

Granular operations remain independent. `prepare_publication()` composes them and persists the
exact candidate, materialized reference pack, validation, readiness and changes—even if blocked.
It returns the snapshot only when required checks pass; otherwise it raises
`PublicationBlockedError(publication=...)` after committing the blocked snapshot and
idempotency outcome. Preparation does not approve or publish the model.

```python
candidate = await model.compile(actor="user:model-editor")
candidate = await model.get_candidate(candidate_id=candidate.id)
report = await model.validate(actor="user:model-editor", candidate=candidate)

publication = await model.prepare_publication(actor="user:model-editor")
# Inspect publication.candidate, publication.reference_pack, publication.validation and
# publication.changes.
# Inspect publication.checks, publication.blockers and publication.nonblocking_questions.

# After the reviewer inspects this publication:
bundle = await model.publish(
    publication=publication,
    version="1.0.0",
    actor="user:model-editor",
    reason="Release this exact reviewed model snapshot.",
)
bundle.model_version
bundle.approval

# In a later request or session, reload a saved preparation by its ID.
stored = await model.get_publication(publication_id=publication.id)
publications = await model.list_publications(limit=50)
versions = await model.list_versions(limit=50)
# The following lookups assume the initial publication succeeded.
published = await model.get_version(version="1.0.0")
changes = await model.diff(before=published, after=candidate)
```

A review UI can replace the preparation call with error handling and inspect either outcome:

```python
from domain_kernel import PublicationBlockedError

try:
    publication = await model.prepare_publication(actor="user:model-editor")
except PublicationBlockedError as error:
    print(f"Publication blocked: {error.publication.id.value}")

    for issue in error.issues:
        print(f"  {issue.severity.value}: {issue.message} [{issue.code}]")
else:
    print(f"Publication prepared: {publication.id.value}")

    for check in publication.checks:
        print(f"  {check.code}: passed={check.passed}, required={check.required}")
        print(f"    {check.message}")

    for question in publication.nonblocking_questions:
        print(f"  Nonblocking question: {question.text}")

    # Publishing remains a separate explicit action.
```

Only successful preparation enters `else`; no additional readiness check or immediate
reload is needed. Use `get_publication()` when reopening a saved snapshot later.

These properties inspect the complete immutable snapshot without I/O; `error.issues`
is the same tuple as `error.publication.blockers`. A caught blocked preparation must
be resolved and prepared again before publication. Applicable checks are collected,
not truncated at the first blocker. Failures that prevent snapshot creation retain
their own typed errors rather than producing a fabricated blocked publication.
Matching idempotency replays return the original ready snapshot or raise with the
original blocked snapshot; after resolving blockers, prepare again with the key omitted or a new caller key.

Required references, definitions, alignments, supported reference pack obligations and
required confirmation evidence block publication until resolved. Only explicitly
reviewed nonblocking model questions may remain, with scope, reason and attribution.
Publication policy cannot waive required obligations. Historical readiness is a
snapshot; publishing rechecks current workspace, review and policy state.
`publish()` records authorization, bundle, audit and idempotency outcome atomically.
Its `Approval` is retained in the bundle, with no separate public approval step.
A matching retry returns the same bundle; a changed actor, reason, version or snapshot
under the same key conflicts, and failed publication leaves no approval or version.
Stale objects, forged snapshot content and cross-model submissions are rejected.
Preparation records differences from the latest version, otherwise the exact baseline,
otherwise an initial empty model. Comparison does not approve unresolved proposals.

## 5. Evidence adapters and optional discovery

File acquisition/parsing are optional adapters. The SDK accepts typed sources;
applications select sources, schedule jobs, and control permissions and inference transport.

For manufacturing PDFs, Docling supplies document structure and normalized evidence
with exact source/location references. Discovery and reconciliation propose meanings
and matches; explicit review establishes the model. Parsing alone neither determines
the business ontology nor populates downstream machine/work-order records. Evidence
retention follows the configured policies; citations do not promise embedded originals.

```python
from domain_kernel import PDF, CopyTo, Excel, ReaderLocation

components = await project.ingest_source(
    actor="user:model-editor",
    source=Excel(location=ReaderLocation(reader="inputs", path="components.xlsx")),
    display_name="Components",
)
source = await project.get_source(name="components")
# Equivalent ID lookup: project.get_source(source_id=components.source_id)
updated_components = await project.ingest_source_revision(
    actor="user:model-editor",
    source_id=source.id,
    source=Excel(path="components-updated.xlsx"),
)
sources_page = await project.list_sources(limit=50, cursor=None)
revisions = await project.list_source_revisions(source_id=source.id, limit=50)
source_revision = await project.get_source_revision(
    source_id=components.source_id, revision_id=components.revision_id
)
source_profile = await project.profile_source(actor="user:model-editor", revision=source_revision)

# path= resolves under the configured inputs reader, whether local or remote.
# Source names are project-local lookup names, independent of paths and revision hashes.

retained = await project.ingest_source(
    actor="user:model-editor",
    source=PDF(path="catalog-policy.pdf"),
    display_name="Catalog policy",
    name="policy",  # Optional override of the generated catalog-policy name.
    retain_original=CopyTo(store="artifacts"),
)
original_copy = await project.copy_source_original(
    actor="user:model-editor", revision=source_revision, destination=CopyTo(store="artifacts")
)
print(f"Verified content hash: {original_copy.verified_hash.value}")
print(f"Artifact store: {original_copy.artifact.store}")
print(f"Artifact key: {original_copy.artifact.key}")
```

Sources use the shared `display_name`, optional `name`, generated `id` convention.
Names are unique within the project's source catalog; display labels may repeat.
`ingest_source()` creates a logical source plus its initial revision. Duplicate names,
including races, raise `SourceAlreadyExistsError` without suffixing or implicit updates.
`get_source()` requires exactly one of `name` or `source_id`; missing sources raise
`SourceNotFoundError`, and foreign IDs raise `ScopeMismatchError`.
`ingest_source_revision()` requires an existing ID and preserves its names/identity.
Naming metadata is excluded from content revision hashes; identical content under
the same source reuses its revision without overwriting recorded provenance.
Individual commands require `actor`; matching idempotent retries replay before acquisition
or collision checks, while changed requests conflict. Atomic metadata/audit/outcome
commits and uniqueness/version guards prevent partial acceptance or lost concurrent
updates; external retention uses the documented recovery contract.

File revisions hash **all original bytes**; provider versions/ETags and processing
fingerprints remain separate. Folder-generated names follow the selection rule below.
Memory processing is bounded with no temporary-file
or disk-spill fallback. Explicit copies retain the exact verified file revision.
Subsequent acquisition verifies pinned bytes or fails; native copies need equivalent
guarantees. Processing transfers bytes into the host process; deployment policy
controls its location, swap and dumps. Caller-owned transports/pools remain caller-owned.

### Ingest batches and folders

`project.ingest_sources()` accepts `Sequence[SourceInput | SourceFolder]`; examples use
lists, immediately frozen by the SDK. Wrap each file descriptor in `SourceInput` with
its naming information; bare descriptors are not batch entries. Configure readers once. This independent example
uses the earlier local `inputs` reader; the same `SourceFolder` parameters work with the remote
`inputs` (S3) and `manuals` (SharePoint) readers from the alternative configuration.
This retry example uses a host-persisted `batch_request_id` from before the first
attempt; retain it when retrying. The keys and per-call limits are optional; the
[basic architecture example](ARCHITECTURE.md#batch-ingestion-and-folder-selection)
inherits the configured limits:

```python
from domain_kernel import (
    CSV,
    PDF,
    Ontology,
    OntologyFormat,
    ReaderLocation,
    SourceFolder,
    SourceInput,
    Word,
)

batch = await project.ingest_sources(
    actor="user:model-editor",
    sources=[
        # path uses the configured inputs reader; each file gets its own catalog identity.
        SourceInput(
            display_name="Suppliers",
            source=CSV(path="suppliers.csv"),  # Defaults: comma delimiter, UTF-8, header row 1.
            idempotency_key=f"{batch_request_id}:suppliers",
        ),
        SourceInput(
            display_name="Catalog rules",
            source=Word(path="catalog-rules.docx"),
            idempotency_key=f"{batch_request_id}:catalog-rules",
        ),
        SourceInput(
            display_name="Company terms",
            source=Ontology(
                path="company-terms.ttl",
                format=OntologyFormat.TURTLE,  # Explicit syntax; Turtle is also the default.
            ),
            idempotency_key=f"{batch_request_id}:company-terms",
        ),
        SourceInput(
            display_name="Installation guide",
            source=PDF(path="installation.pdf"),
            idempotency_key=f"{batch_request_id}:installation",
        ),
        SourceFolder(
            location=ReaderLocation(reader="inputs", path="technical-documents"),
            recursive=True,
            include=["**/*.pdf", "**/*.docx"],
            exclude=["**/archive/**"],
            name_prefix="technical",
            idempotency_key=f"{batch_request_id}:technical-folder",
        ),
    ],
    # Explicit per-call limits for this advanced example; omit to inherit configuration.
    max_concurrent_sources=2,
    max_files=500,
)
print(f"Ingested {len(batch.successes)} sources; {len(batch.failures)} failures.")
for failure in batch.failures:
    # A failure may identify a file or an incompletely listed folder; non-file inputs have no location.
    location = failure.location
    source_label = (
        f"{location.reader}:{location.path}" if location is not None else "Non-file input"
    )
    print(
        f"{source_label} — {failure.stage.value}: "
        f"{failure.message} "
        f"[code={failure.code}, retryable={failure.retryable}]"
    )

# Retry only inputs marked retryable; the returned result does not mutate the original batch.
retry_inputs = [failure.input for failure in batch.failures if failure.retryable]
if retry_inputs:
    retried = await project.ingest_sources(actor="user:model-editor", sources=retry_inputs)

# Discover only when the original batch is complete and contains evidence.
if batch.failures:
    print("Review failures and any retry results before deciding whether to continue.")
elif batch.revisions:
    batch_run = await model.discover(
        actor="user:model-editor",
        sources=batch.revisions,
        idempotency_key=f"{batch_request_id}:discovery",
    )
else:
    print("No sources were selected.")
```

`SourceInput` accepts the single-source naming, descriptor, retention and retry fields.
`SourceFolder` selects files; `recursive=False` (default) ignores subfolders, while True
descends. Include/exclude use case-sensitive relative-path globs (`**` includes zero
levels); exclusions win. Empty include selects all files, and unsupported formats are
reported. Exclude and explicitly supply files needing custom names or parser options.
All paths stay within reader roots; `.` selects the root. S3 uses slash-boundary prefixes.

Folder display names are filename stems; stable names derive from optional name_prefix
plus the relative path without its final extension using the shared slug rules. IDs are
independent. Invalid/generated duplicate names fail; no suffixes, implicit updates or
removals. Identical overlapping requests coalesce; conflicting options/names fail.

Per-call concurrency/max_files inherit and cannot exceed configured ceilings. Client-wide
bounded workers, paginated listing and SourceSelectionLimits bound processing/enumeration.
Defaults: 1,000 selected files, 10,000 listing entries, depth 32, 60 seconds of enumeration;
filtered entries still consume listing budgets. Exceeding budgets cannot truncate success.
Batch results preserve input/path order and expose items/successes/failures/revisions as
immutable views. Failures include LISTING/NAMING/INGESTION stage, location and sanitized
Issue/retryability. Direct read-only `failure.message`, `failure.code` and
`failure.severity` delegate to that same `issue`; severity is an `IssueSeverity` enum.
Use `failure.issue` for the full structured diagnostic, including its path; convenience
properties do not duplicate serialized fields. Incomplete folders import no files;
other selections can proceed. `batch.revisions` includes only successes, so the caller
must decide whether partial evidence is sufficient before discovery.
Each source commits independently with actor audit. Cancellation/fatal coordination
failures propagate; caller errors fail preflight. Empty folders are valid.

Folder keys persist complete manifests and generated child keys before content ingestion;
replays keep selections, names/options and available provider pins, with no new arrivals.
Generated child keys also preserve these guards on subset retries. Capture metadata/audit/
idempotency commit together; child successes remain independently replayable. A failed
listing retries until its first complete capture; without caller keys no cross-call replay
is promised. A new scan does not imply an atomic folder snapshot or source revision update.
Retry results cover only the retried selections; the original batch stays immutable.
Resubmitting the original selections with the same keys obtains a refreshed full result.
See the [full contract](ARCHITECTURE.md#batch-ingestion-and-folder-selection).

### Customize discovery instructions

Both `model.discover()` and `model.extract_proposals()` accept optional keyword-only
`additional_instructions` and `prompt_override` strings. Without either, use the
versioned SDK default. Additional instructions extend that default; an override
replaces it and ignores additional instructions. Reject supplied blank strings
before work begins. Model context and evidence remain separate inputs.

```python
run = await model.discover(
    actor="user:model-editor",
    sources=[legislation.revision],
    additional_instructions=(
        "Propose recruitment-related meanings, responsibilities and safeguards. "
        "Retain relevant definitions, qualifications and cross-references elsewhere."
    ),
)
print(run.prompt.effective_instructions)

# Independent focused run: the override replaces the default discovery instructions.
focused = await model.extract_proposals(
    actor="user:model-editor",
    source_revisions=[legislation.revision],
    prompt_override=(
        "Propose definitions for instructions for use, their provider and deployer "
        "roles, fields and relevant qualifications. Cite the supporting passages "
        "and flag uncertain interpretations for review."
    ),
)
```

`legislation.revision` is an already ingested, exact source revision. Prompt controls
do not replace `ModelRequest.response_schema_json`: the SDK supplies and validates
its proposal schema in every mode. Existing bounded retry, error, per-source failure
and recovery behavior stays unchanged. Invalid output cannot become a valid proposal;
there is no silent fallback from an override to default instructions.

Persist an immutable `DiscoveryPrompt` capture on draft/result `.prompt`, containing
both supplied values, effective instructions, default version when used and schema
version. Pin the exact prompt/schema/context in the processing fingerprint. Retries
and `resume_discovery()` reuse that capture; new instructions require a new run.
Idempotency identity includes both arguments, including ignored additional text.

The tutorial passes the full original AI Act, then uses additional instructions to
focus on recruitment. Relevant cross-references remain available. This guides proposed
meanings; it neither selects pages nor guarantees an exact or exhaustive result. The
curated passage/model expectations must be evaluated against actual extraction,
including omissions and irrelevant proposals. The override exercise stays in a
separate model copied from the seed publication and does not change the main story.

### Discover from ingested revisions

This recovery example uses separate host-persisted `discovery_request_id` and
`resume_request_id` values for the discovery request and a later resume request.
Each survives retries of its own operation. A basic discovery call omits the key;
resuming requires the existing run ID, not another call to `discover()`.

```python
from domain_kernel import PDF, CaseStatus, RunStatus

# Reuse the model from the original client configured with model_gateway=gateway.
manual = await project.ingest_source(
    actor="user:model-editor",
    display_name="Component policy",
    source=PDF(path="component-policy.pdf"),  # Uses the configured inputs reader.
    idempotency_key=f"{discovery_request_id}:capture-policy",
)
run = await model.discover(
    actor="user:model-editor",
    sources=[source_revision, manual.revision],
    idempotency_key=discovery_request_id,
)
saved_run = await model.get_discovery_run(run_id=run.id)
runs = await model.list_discovery_runs()
# In a later worker, after addressing recoverable failures, resume the existing run.
if saved_run.status in [
    RunStatus.PARTIALLY_FAILED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
]:
    run = await model.resume_discovery(
        actor="user:model-editor", run_id=saved_run.id, idempotency_key=resume_request_id
    )
else:
    run = saved_run

# Inspect the latest returned snapshot; resumption can still leave failures or pending cases.
print(f"Discovery {run.id.value}: {run.status.value}")

# Discovery can return useful proposals alongside source-specific failures.
for failure in run.failures:
    print(
        f"{failure.source_label} — {failure.severity.value}: "
        f"{failure.message} "
        f"[code={failure.code}, retryable={failure.retryable}]"
    )

if run.status in [
    RunStatus.PARTIALLY_FAILED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
]:
    print("Discovery is incomplete; inspect the outcome before continuing.")

# Use the default page size and retrieve pending cases from this run.
pending = await model.list_review_cases(
    run_id=run.id,
    status=CaseStatus.PENDING,
)
displayed_cases = 0

while True:
    for case in pending.items:
        displayed_cases += 1
        print(f"\nCase {case.id.value}: {case.kind.value}")
        print(f"  Reason: {case.reason}")

        # These are the definition snapshots provided for inspecting this case.
        for definition in case.definitions:
            print(f"  Definition: {definition.display_name} ({definition.name})")

        # Some cases ask for clarification rather than proposing a definition.
        if case.question is not None:
            print(f"  Question: {case.question.text}")

        # Citations remain references; excerpts require explicit evidence retrieval.
        print(f"  Evidence citations: {len(case.evidence)}")

    # Continue until every page has been inspected, retaining the same filters.
    if pending.next_cursor is None:
        break
    pending = await model.list_review_cases(
        run_id=run.id,
        status=CaseStatus.PENDING,
        cursor=pending.next_cursor,
    )

if displayed_cases:
    print(f"\nDisplayed {displayed_cases} pending review cases.")
else:
    # An empty review queue does not prove that discovery completed successfully.
    print("\nNo pending review cases were found for this run.")

# Independent stages; same model context and stored state.
draft = await model.extract_proposals(actor="user:model-editor", source_revisions=[source_revision])
alignment = await model.propose_alignment(actor="user:model-editor", discovery_id=draft.id)
alignment = await model.get_alignment(alignment_id=alignment.id)
stage_cases = await model.list_review_cases(
    reconciliation_id=alignment.id, status=CaseStatus.PENDING, limit=50
)
```

Discovery accepts ingested revisions only; named source creation or revision ingestion
is explicit, with no anonymous source creation from descriptors. Inference yields
proposals. Stable identities and compatible approved mappings can
be reused; similar labels with different meanings remain distinct review work.
`DiscoveryResult.failures` contains `DiscoveryFailure` records. Their direct read-only
`message`, `code` and enum `severity` properties delegate to the same `issue`, without
duplicating serialized fields. `.issue` retains the full structured diagnostic.
Run failures and pending cases can coexist; an empty queue does not imply success.
Resume returns a new result snapshot for the same run ID; inspect that snapshot and
reload case pages with the same filters. Inspection never accepts proposals.
Deterministic reconciliation/editing/validation/publication do not require inference.
Unknown required validators and missing optional capabilities fail explicitly.
Checkpointed SDK operations persist results and return; application workers and
human-decision orchestration are outside the library.

For sequential inspection, an optional iterator performs the same bounded page
reads without caller-managed cursors:

```python
async for case in model.iter_review_cases(
    run_id=run.id,
    status=CaseStatus.PENDING,
):
    print(f"{case.id.value}: {case.reason}")
```

Call the factory without `await`; `async for` performs I/O lazily. `page_size`
defaults to 50 and `cursor` can select a starting page. Filters and ordinary cursor
semantics stay unchanged; no prefetching, transaction across yields, automatic
decisions or stronger snapshot guarantee. Stopping early makes no further calls;
errors propagate. Keep `list_review_cases()` for UI pages or explicit resume cursors.

The [backend examples](ARCHITECTURE.md#backend-requests-and-workers) show direct SDK
calls in separate worker/request actions. Retain operation-specific request IDs
before the first attempt, display persisted run failures and page continuation,
then preview and explicitly submit the same inspected case and chosen decision.
Do not reload the latest case to replace the inspected version at submission.
Blocked preparations remain displayable diagnostics; publication uses the exact
inspected immutable publication ID after explicit authorization. Resolving blockers
requires a new preparation intent, not replay of the old blocked preparation key.

## 6. Supply already-parsed evidence

A host parser can provide text, tables or semantic fragments without another file
acquisition/parsing pass. Reuse the existing client/project/model, configured in
section 1 with a `ParsedSourceProvider` named `content-platform` and the host's
`parsed_source_resolver`. It implements `ParsedSourceResolver` and reconstructs exact
captures under the host's access policy. `ParsedSourceOrigin.provider` selects the
provider by its `name`; registration does not invoke retrieval. The same handles
support ingestion, discovery and review, with the existing optional model gateway.

```python
from datetime import datetime, timezone
from domain_kernel import (
    ExternalLocation,
    ParsedSource,
    ParsedSourceOrigin,
    ParsedTable,
    ParsedText,
)

parsed_source = ParsedSource(
    origin=ParsedSourceOrigin(
        provider="content-platform",  # Matches ParsedSourceProvider.name at startup.
        document_id="catalog",
        document_revision="v7",
        captured_at=datetime.now(tz=timezone.utc),
    ),
    parts=[
        ParsedText(
            text="Part is the local name for Component.",
            locator=ExternalLocation(key="section:terminology"),
        ),
        ParsedTable(
            name="components",
            columns=["number", "description"],
            rows=[["C-123", "Housing"]],
            locator=ExternalLocation(key="table:components"),
            row_locators=[ExternalLocation(key="row:C-123")],
        ),
    ],
)
captured = await project.ingest_source(
    actor="user:model-editor", source=parsed_source, display_name="Parsed catalog"
)
parsed_run = await model.discover(actor="user:model-editor", sources=[captured.revision])

# Select a citation returned by ingestion; citations do not embed their excerpts.
if captured.evidence:
    citation = captured.evidence[0]
    evidence_content = await project.get_evidence(evidence=citation)
    print(evidence_content.excerpt)
else:
    print("No evidence citations were returned for this source.")
```

The revision hashes the **canonical parsed-source capture**, including upstream
identity/revision and locators, excluding acquisition timestamps. An upstream
original digest is a labelled host assertion, not proof the SDK read those bytes.
Parsed content follows derivative-retention policy. Later discovery/evidence
access uses retained content or the configured resolver and recomputes its digest;
unavailable or changed content fails. Retention defaults do not promise replay.
`get_evidence()` accepts an existing `Evidence` citation and returns `EvidenceContent`
with the loaded `excerpt`, its `evidence` citation and verified acquisition `origin`.
`copy_source_original` accepts file origins only; statement/parsed-source captures have no original file.

## 7. Attributed statements and model decisions

```python
from datetime import datetime, timezone

from domain_kernel import ConfirmStatement, PersonId, StatementForm, StatementIntent

from domain_kernel import Person, Statement

# The host supplies the speaker's stable identity.
speaker = Person(
    id=PersonId(value="person:domain-owner"), name="Domain owner", role="Catalog owner"
)
statement = await project.ingest_source(
    actor="user:model-editor",
    source=Statement(
        text="Component numbers identify catalog entries, not individual physical units.",
        speaker=speaker,
        # recorded_by defaults to this ingestion's actor; stated_at may be omitted if unknown.
        stated_at=datetime(year=2026, month=11, day=1, tzinfo=timezone.utc),
        context="Component catalog identifiers",
        form=StatementForm.QUOTATION,
        intent=StatementIntent.ASSERTION,
    ),
    display_name="Identifier definition",
)
confirmation_evidence = await project.ingest_source(
    actor="user:model-editor",
    source=Statement(
        text="I confirm the recorded component identifier definition.",
        speaker=speaker,
        recorded_by="user:recorder",  # Preserve a different recorder explicitly.
        stated_at=datetime(year=2026, month=11, day=2, tzinfo=timezone.utc),
        context="Confirmation of recorded definition",
        form=StatementForm.QUOTATION,
        intent=StatementIntent.ASSERTION,
    ),
    display_name="Identifier confirmation",
)
confirmation_action = ConfirmStatement.from_statement(
    source=confirmation_evidence,
    authority="Owner of this definition",
    reason="Record separately supported confirmation.",
)
```

Captures retain speaker, role, resolved recorder, dates, context, form and intent.
`context` is required, non-blank text qualifying where the claim applies; it does not
override a model description. `form` and `intent` remain explicit, required choices.
Omitted or `None` `recorded_by` means the ingestion actor is recording the statement;
resolve and persist that identity once before capture hashing, including batch and
source-revision ingestion. An explicit recorder remains independent of the operation's actor.
Omitted or `None` `stated_at` means unknown; supplied times must be timezone-aware.
The SDK records ingestion time separately as `recorded_at`, never as a substitute for
`stated_at`. Matching retries preserve the original attribution and timestamps.
The versioned capture digest includes the resolved recorder, context and original
statement time (canonical null when unknown); `recorded_at` stays outside the digest.
Recorded confirmation remains distinct from an authenticated action. Host applications
verify identity and authority; the SDK enforces model-level evidence obligations.

`ConfirmStatement.from_statement(source=..., authority=..., reason=...)` is a pure,
synchronous factory over the captured `IngestedSource`. It copies the statement's
speaker, original `stated_at`, recorder and capture `recorded_at`, plus its evidence;
sets `ConfirmationMethod.RECORDED` and `authenticated_actor=None`; and returns the
ordinary decision with its complete `Confirmation` payload. It reads no clock and
performs no I/O, inference, persistence or approval. Authority and reason stay explicit
and non-blank; selecting a capture does not establish its truth or the speaker's authority.

Raise `InvalidDecisionError` for a non-statement capture, missing original statement
time, empty evidence, citations inconsistent with the exact revision, or invalid
attribution/timestamps. Never substitute ingestion time for an unknown confirmation
time. Ordinary ingestion still permits unknown `stated_at`. Normal review submission
rechecks stored provenance, project scope, evidence requirements and case compatibility.
No wire fields or discriminators change; direct confirmation constructors remain
available for explicitly supplied records, including authenticated confirmations.

The reference example below uses separately inspected `reference_case`,
`local_definition` and `reference_definition` snapshots; the reference belongs to
the model's selected pack.

```python
from domain_kernel import CaseKind, CaseStatus

from domain_kernel import (
    AnswerQuestion,
    ApproveLocalExtension,
    ConfirmStatement,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    Reject,
)

# Only submit actions compatible with an inspected case; IDs below are illustrative.
review_page = await model.list_review_cases(
    run_id=parsed_run.id, status=CaseStatus.PENDING, limit=50
)
if review_page.items:
    case = await model.get_review_case(case_id=review_page.items[0].id)
    if case.kind == CaseKind.SOURCE_ALIGNMENT:
        component = await model.get_concept(name="component")
        decision = case.same_as(
            definition=component,
            reason="Same meaning and scope as the approved definition.",
        )
        impact = await model.preview_changes(case=case, decision=decision)
        print(f"Previewed workspace revision: {impact.workspace_revision}")

        # Mapping a source to an existing definition may leave definitions unchanged.
        print(f"Definition changes: {len(impact.definition_changes)}")
        for change in impact.definition_changes:
            print(f"  Change: {change.kind.value}")
            for definition in change.before:
                print(f"    Before: {definition.display_name}, revision {definition.revision}")
            for definition in change.after:
                print(f"    After: {definition.display_name}, revision {definition.revision}")

        # Inspect how source proposals would map to model definitions.
        print(f"Source alignment changes: {len(impact.source_alignment_changes)}")
        for change in impact.source_alignment_changes:
            alignment = change.after
            if alignment is not None:
                print(f"  Proposal: {alignment.proposal_id.value}")
                print(f"  Disposition: {alignment.disposition.value}")
                if alignment.definition_id is not None:
                    print(f"  Definition: {alignment.definition_id.value}")
                    print(f"  Definition revision: {alignment.definition_revision}")
            elif change.before is not None:
                print(f"  Remove alignment for proposal: {change.before.proposal_id.value}")

        print(f"Affected review cases: {len(impact.affected_case_ids)}")
        for case_id in impact.affected_case_ids:
            print(f"  {case_id.value}")

        print(f"Invalidated decisions: {len(impact.invalidated_decision_ids)}")
        for decision_id in impact.invalidated_decision_ids:
            print(f"  {decision_id.value}")

        if impact.blockers:
            print("This decision has blockers:")
            for blocker in impact.blockers:
                print(f"  {blocker.severity.value}: {blocker.message} [{blocker.code}]")
        else:
            print("No blockers found in this preview. The decision has not been submitted.")
        # In a separate action, after the reviewer confirms the inspected preview:
        result = await model.decide_review(
            case=case,
            decision=decision,
            actor="user:model-editor",
        )
        print(f"Committed decision: {result.decision_id.value}")
        print(f"Workspace revision: {result.workspace_revision}")
    history_page = await model.get_review_history(case_id=case.id, limit=50)
    print(f"History records on this page: {len(history_page.items)}")
    for record in history_page.items:
        print(f"Decision: {record.id.value} ({record.action.kind})")
        print(f"  Recorded by {record.actor} at {record.recorded_at.isoformat()}")
        print(f"  Reason: {record.action.reason}")
    if history_page.next_cursor is not None:
        print("More history is available.")
        # Fetch the next page with cursor=history_page.next_cursor and the same case_id.

# Additional typed model decisions, submitted through the same preview/decide contracts.
EditDefinition(
    definition_id=component_id,
    name="component",
    display_name="Component",
    meaning="A catalog item.",
    body=ConceptDefinition(),
    reason="Clarify existing meaning.",
)
# These are separately inspected reference-case/local/pinned-reference snapshots.
reference_decision = reference_case.same_as(
    local_definition=local_definition,
    reference_definition=reference_definition,
    reason="Reviewed against the pinned reference definition.",
)
ApproveLocalExtension(definition_id=component_id, reason="Explicit reviewed local meaning.")
Exclude(scope_text="Catalog schema", reason="Instance-only field is outside this model's scope.")
Reject(reason="The source text is a heading, not a definition.")
Defer(
    question="Is the identifier unique within a catalog or across catalogs?",
    reason="Meaning unresolved.",
)
AnswerQuestion(answer="Unique within a catalog.", reason="Recorded model clarification.")
ConfirmStatement.from_statement(
    source=confirmation_evidence,
    authority="Owner of this definition",
    reason="Record separately supported confirmation.",
)
KeepNonblockingQuestion(
    scope_text="Optional alias spelling", reason="No required obligation depends on it."
)
```

### Correct a previously reviewed interpretation

In this optional branch, `resolved_case_id` identifies a resolved source-alignment
case in `model`, `selected_proposal_ids` selects occurrences from that case,
and `correct_definition_id` names the inspected correct active local definition.

```python
resolved = await model.get_review_case(case_id=resolved_case_id)
correct = await model.get_definition(definition_id=correct_definition_id)
correction = await model.reopen_review_case(
    actor="user:model-editor",
    case_id=resolved.id,
    expected_version=resolved.version,
    proposal_ids=selected_proposal_ids,
    reason="These selected occurrences refer to a different business concept.",
)
corrected_mapping = correction.same_as(
    definition=correct,
    reason="Reviewed the selected evidence against this definition and scope.",
)
correction_impact = await model.preview_changes(case=correction, decision=corrected_mapping)
# Inspect correction_impact.source_alignment_changes and correction_impact.affected_case_ids.
# After inspecting the impact, apply only this selected occurrence scope:
await model.decide_review(
    case=correction,
    decision=corrected_mapping,
    actor="user:model-editor",
)
```

`reopen_review_case` creates a new case with `correction_of_decision_id`; it preserves the original
case/decision. Omit `proposal_ids` for its whole effect; a nonempty subset is allowed
only for source-alignment corrections. Explicit occurrence selection also permits
correcting mapping effects from an earlier `Accept` of a definition proposal; the
new source-alignment case leaves its definition approval intact. Without that
selection, reopening definition-lifecycle decisions is invalid: use revision,
retirement or restoration proposals instead. The successful new decision records
`supersedes_decision_id` and its exact `proposal_ids`, leaving other mappings intact.
Rejecting the correction preserves the old interpretation and can cancel obsolete
pending correction work with the current case version. Applying a stale or overlapping
correction fails; approved definition revisions/retirements use their dedicated APIs.

Source-case `same_as(definition=..., reason=...)` retains the inspected definition snapshot and derives
its ID/revision. Preview and submission validate its exact content, active local
status and scope; stale, modified or foreign targets fail without substituting
a newer revision. Source alignment changes do not necessarily change definitions.

For reference alignment, use `same_as`, `narrower_than`, `broader_than`, `related_to`
or `distinct_from`, each with `local_definition`, `reference_definition` and `reason`.
They express the local meaning relative to the reference meaning and select the stored
relation automatically. Both snapshots and the exact containing-pack pin are retained;
preview/submission recheck scope, revisions, pin and content without substitution.
These synchronous case methods construct typed decisions, not booleans or writes.
Invalid argument forms fail explicitly; incompatible case kinds raise `InvalidDecisionError`.

For example, a document's **Automobile** can mean the company's **Car** concept:
source-case `same_as(definition=car, reason=...)` prepares that interpretation.
The reference **Vehicle** includes cars, motorcycles and trucks. Reference-case
`narrower_than(local_definition=car, reference_definition=vehicle, reason=...)`
declares that every Car is a Vehicle, but not every Vehicle is a Car. Narrower/broader
mean strict inclusion of meanings, not confidence; reference `same_as` means equivalent
meaning, `related_to` asserts no inclusion, and `distinct_from` does not imply disjointness.
None merges identities or grants formal ontology equivalence/inheritance. Preview and
submission remain separate async actions; constructors do not infer or prove the judgment.

`ReviewImpact` includes the inspected workspace revision, proposed changes, affected
cases, invalidated decisions and blockers. Rejection reports both rejected and
released cases in `affected_case_ids`; the parent's `generated_member_case_ids`
distinguishes generated members. Preview reserves nothing; both review methods
validate the supplied case's identity, scope, version and content against stored state.
`decide_review` recomputes dependent impact in its transaction. Matching idempotent
retries replay before stale checks; different request content under a key conflicts.
Acceptance checks relevant target/workspace guards. Rejection can cancel obsolete
target intent but still requires the current case version and intact reservations.
Incompatible or uncertain dependencies become stale and require re-review. Pending
required corrections and stale decisions block new publication, while historical
bundles remain valid snapshots of what was previously approved.

Required gaps remain blockers. Optional model questions need an explicit reviewed
nonblocking disposition. App-specific tasks, deadlines and business recommendations
are not model decisions. Decisions and idempotency outcomes are scoped by project/model.

<a id="8-reference-assets-baselines-and-model-structure"></a>

## 8. Reference assets, model copies and model structure

Reference pack catalog assets below are illustrative fixtures, not shipped industry content.
Patterns are reusable definition graphs. The SDK imports/remaps them; applications
select them and decide their business applicability. A catalog author composes
reference assets into a versioned reference pack with pinned dependencies, provenance,
licenses, explicit obligations and supported validator versions. Identity conflicts
must be resolved explicitly; names alone do not establish equivalence. Technical
reference architectures, assignment methodology and ERP installation templates stay
in the application; their business-semantic portions can be represented in reference packs.

The following creates a separate design by copying a published model with `copy_from`
and selecting a reference pack. Copying is useful for observed/proposed alternatives;
it is not required to change packs on an existing, unpublished model. That reviewed
transition is shown below. Pack assets and published model versions remain immutable.
The selected pattern introduces names not already used by the copied model; existing
definitions can be reused only through explicit mappings, never by matching labels.

```python
from domain_kernel import ModelKind

reference_pack = await client.get_reference_pack(key="example.catalog", version="1.0.0")
reference_packs = await client.list_reference_packs(limit=50)
# Inspect reference_pack.definitions, reference_pack.patterns and reference_pack.dependencies.
pattern = reference_pack.get_pattern(name="catalog-pattern")  # Loaded snapshot; no I/O.
print(f"Pattern: {pattern.display_name} — {pattern.description}")

# Create an independent model from this exact published version.
reference_model = await project.create_model(
    actor="user:model-editor",
    display_name="Reference Derived",
    description="Component catalog copied from a published model and adapted with reference knowledge.",
    kind=ModelKind.PROPOSED,
    reference_pack=reference_pack,
    copy_from=published,
)
print(f"Created {reference_model.info.display_name} ({reference_model.info.name})")

pattern_case = await reference_model.propose_pattern(
    actor="user:model-editor",
    pattern=pattern,
    reason="Instantiate the selected pinned reference graph.",
)
print(f"Review case: {pattern_case.id.value}")
for change in pattern_case.proposed_changes.changes:
    print(f"Change: {change.kind.value}")
    for definition in change.after:
        print(f"  {definition.display_name} ({definition.name}): {definition.meaning}")
# Inspect/remap bindings and resolve required alignments through ordinary review.
```

Patterns use `display_name`, a generated name slug with optional override, and an
independent generated ID. Names are unique within the materialized pack; duplicates
fail without suffixes. `get_pattern()` accepts exactly one of `name` or `pattern_id`,
performs an exact in-memory lookup, and raises `PatternNotFoundError` when absent.
Adoption accepts that inspected pattern directly, verifies its exact containing pack
pin and full content against the selected pack, and records both in request identity
and provenance. Unassociated, foreign or modified snapshots fail without substitution.
No adoption namespace is needed: local IDs are generated, model-local names remain
unique, and collisions fail atomically without automatic prefixes/suffixes or merging.

`copy_from` accepts a published `DomainModelBundle`; omission/`None` means no copy.
The SDK reloads its publication in the same project and verifies scope, identity,
content hash and integrity before creating the new model. It rejects live models,
version references, foreign-project or unregistered bundles and forged content.
Dependencies remain explicit immutable version pins in that project. There are no
implicit sibling draft reads or substitutions of the latest source publication.
Reference imports preserve upstream meanings and mint local identities for differences.
Pattern proposals remap all internal
references atomically, validate existing bindings and retain upstream provenance.
Required reference dispositions cannot be satisfied by an undecided import. Apply
patterns incrementally, bind existing local definitions by exact revision with
`DefinitionBinding`, and review local divergences. Copied definitions get local IDs
and remapped references, with `baseline_definition_id` preserving direct lineage.
The `baseline` metadata records `copy_from.model_version` as a provenance pin;
lineage alone does not embed the source bundle. Source dependency pins carry forward;
new pins cannot conflict.
The source stays immutable, later publications do not update the copy, and the new
model follows its own review/publication lifecycle without inheriting approval.

### Compose and validate a reference pack

Reference-pack value methods need no client, database or inference gateway.
Inputs are typed content and already-loaded packs. These named catalog packs,
patterns and obligation IDs are illustrative fixtures; inspect the selected content.

```python
from domain_kernel import ObligationId, PackMaturity

from domain_kernel import (
    ReferencePackImport,
    ReferencePackSpec,
    ReferencePack,
)

procurement_pack = await client.get_reference_pack(key="example.procurement", version="1.0.0")
manufacturing_pack = await client.get_reference_pack(key="example.manufacturing", version="1.0.0")
spec = ReferencePackSpec(
    key="example.manufacturer",
    version="1.0.0",
    title="Manufacturer business reference pack",
    applicability="Procurement and manufacturing vocabulary for the selected scope.",
    exclusions=["Operational rule execution"],
    maturity=PackMaturity.EXPERIMENTAL,
    provenance="Explicit composition of inspected procurement and manufacturing inputs.",
    license="License selected by the author after reviewing input licenses.",
    semantic_mapping_version="1.0",
    imports=[
        ReferencePackImport(
            reference_pack=procurement_pack,
            namespace="procurement",
            pattern_ids=[procurement_pack.get_pattern(name="purchase-order").id],
            obligation_ids=[ObligationId(value="order-supplier")],
        ),
        ReferencePackImport(
            reference_pack=manufacturing_pack,
            namespace="manufacturing",
            pattern_ids=[manufacturing_pack.get_pattern(name="component-catalog").id],
            obligation_ids=[],  # Deliberately import vocabulary/patterns without its obligations.
        ),
    ],
)
build = ReferencePack.compose(
    spec=spec, actor="user:pack-author", reason="Define this explicitly scoped combination."
)
# Inspect build.validation.issues and build.validation.required_capabilities.
if build.pack is not None:
    composed_pack = build.pack
    validation = composed_pack.validate()
    payload = composed_pack.serialize()
    received_pack = ReferencePack.deserialize(payload=payload)
    schema = ReferencePack.get_json_schema()
```

Imports materialize all definitions into distinct namespaces and remap the selected
patterns/obligations. Namespaces match `[A-Za-z][A-Za-z0-9_-]*`; definition, pattern
and obligation ID values become `namespace + ":" + original_id.value`. For example, an original
`Supplier` becomes `procurement:Supplier`, which local additions may reference.
These composition namespaces remain; pattern adoption takes no namespace. Imported
pattern names/display names are preserved, and duplicate names fail validation.
Body-local attribute/activity/role/condition IDs keep their existing scope. `ReferenceOrigin` preserves source pack/definition identities;
labels never trigger merging. The spec can also contain explicitly authored
`ReferenceDefinition`, `Pattern` and `ReferencePackObligation` values. Duplicate IDs,
dangling references, dependency conflicts and unsupported remapping produce `Issue`
diagnostics and no usable pack. Formal expressions need supported semantic mappers;
prose is not rewritten by string substitution. No external resources are fetched.

Pattern IDs/names survive serialization without regeneration. The containing-pack
pin on a loaded pattern is runtime context, excluded from embedded pattern bytes
and reattached after load/composition; adoption hashes that pin explicitly. This
avoids a self-referential pack hash while retaining the exact selection origin.

Pattern selection defaults to empty. Each import explicitly selects obligations,
including an empty selection when intended. Selected requiredness is preserved;
omitted obligations appear as complete original snapshots in the composition
manifest. Required-omission warnings can therefore be reproduced after reload. Author and rationale are recorded. The output is a new scoped pack, not
a certification against all imported packs. Structural validation reports required
capabilities; adopting the pack also checks their availability in the host.

`reference_pack.serialize()`/`ReferencePack.deserialize()` and
`ReferencePack.get_json_schema(schema_version="1.0")`
use the same closed format as catalog lookup: explicit tags/fields, canonical hash
excluding `pin.content_hash`, strict references and bounded decoding. Unknown versions
raise `UnsupportedReferencePackVersionError`; malformed/inconsistent packs raise
`InvalidReferencePackError`. Loading performs no model validation or evidence fetch.

After successful composition, the caller publishes `payload` through its approved catalog channel. Host catalog
writes must reject different content at the same key/version; unchanged content may
be replayed. There is no automatic registry upload or mutable pack overwrite.

### Change packs without publishing first

This optional branch can run on an existing model with no published version, even
if the current pack has unresolved publication blockers. It changes the working
model's pack selection through review, preserving the model and company identities.
The same operation attaches a first pack or explicitly removes one with
`reference_pack=None`; its target argument has no default. `None`-to-`None` and
same-pin requests fail as no-ops. Removal clears active reference metadata and
pack-only requirements while retaining their audit history and all core checks.

```python
pack_case = await model.propose_reference_pack_change(
    actor="user:model-editor",
    reference_pack=composed_pack,
    expected_workspace_revision=model.info.revision,
    reason="Adopt the explicitly scoped reference pack for this business.",
)
pack_decision = Accept(reason="Reviewed changed obligations and required re-review.")
pack_impact = await model.preview_changes(case=pack_case, decision=pack_decision)
# Inspect pack_case.reference_pack_change, pack_impact.invalidated_decision_ids and
# pack_impact.blockers.
# After inspection; no intervening workspace edit:
await model.decide_review(
    case=pack_case,
    decision=pack_decision,
    actor="user:model-editor",
)
```

The case contains complete before/after pack snapshots, obligation changes and
impacted definitions. It is guarded by the post-creation workspace revision, so its
own creation does not make it stale. Subsequent workspace changes do: reject and
re-propose against current state. Same-pin requests and a second pending pack change
are rejected. `Reject` preserves the active pin even with obsolete workspace/target
guards; pass the current inspected case, not an outdated case version.

Acceptance requires target capabilities and atomically changes the working pin,
records exact applied effects and creates required re-review work. Company meanings
and IDs remain; reference-metadata changes append definition revisions, clearing
old-pack alignments from current content while retaining their history. Compatible
source mappings may be deterministically rebound; uncertain mappings and affected
confirmations require re-review. Pending authoring work is rechecked in the new context.

Old pack-specific blockers do not prevent the transition. New pack obligations, core
integrity and evidence requirements still gate publication. Removed obligations are
explicit scope changes in the audit, never a claim that the old requirements passed.
Previously prepared publications become stale for new publication; existing
published bundles retain their original pack. The host authorizes pack changes.
Pack changes never repin published model dependencies implicitly. Release pending
coordinated groups before proposing a pack change; grouping is rejected while a pack
change is pending. Unresolved individual review cases can remain.

Cases carry `ReviewRequirement` origins distinguishing core/evidence gaps from exact
pack obligations. Acceptance marks generated pending/deferred old-pack-only cases
and their unresolved questions `superseded`, advances case versions and links
`superseded_by_decision_id` to the pack-change decision, without inventing answers or
confirmations. Resolved/reviewed historical cases and questions remain unchanged;
their old requirements and optional exceptions are inactive for current readiness. The change preview
lists `superseded_case_ids`. New pack requirements create fresh cases; obsolete cases
no longer contribute to `pending_required`. Mixed/core/evidence cases and manual
proposals remain; readiness considers their still-active requirements. Superseded
cases stay inspectable but cannot be decided or reopened. Stale manual intent can
be cancelled/reproposed against the current definition revisions.

### Compare a model with its baseline

```python
reference_candidate = await reference_model.compile(actor="user:model-editor")
baseline_changes = await reference_model.diff(
    before=published,
    after=reference_candidate,
)
print(f"Compatibility: {baseline_changes.compatibility.value}")
for change in baseline_changes.changes:
    before_names = [definition.name for definition in change.before]
    after_names = [definition.name for definition in change.after]
    print(f"{change.kind.value}: {before_names} -> {after_names}")
# Inspect baseline_changes.comparison and baseline_changes.correspondences.
# Inspect baseline_changes.reference_disposition_changes.
```

This same path compares an observed business model with a proposed design created
from its published baseline. `after` belongs to the called model; `before` must be
from that model or its exact direct baseline. Other sibling comparisons are rejected.
Both arguments accept `DomainModelBundle`, `ModelVersion` or `Candidate`, including
mixed forms. The async method reloads exact stored snapshots, verifies supplied
objects by scope, identity, hashes and full content, and normalizes bundles to version
references for the existing comparison engine. Equivalent bundle/reference calls
produce identical changes and snapshot pins; no wire fields or embedded bundles are
added. Deserialized bundles must match registered publications. Malformed bundles,
missing publications and altered snapshots fail with the existing typed errors;
there is no import, latest-version substitution or implicit candidate compilation.
Cross-model comparison accepts only the exact source publication pinned by `after`,
not another model's candidate. Comparison creates no audit records and does not
approve pending work or establish readiness; compile again after review decisions.
`ChangeSet` identifies snapshots, reference pack/dependency pins, definition changes including
retirement/replacement, and source/reference disposition changes. Lineage determines
correspondence and normalizes references; labels never do. Unmatched occurrences are
additions/removals. Compatibility describes the model contract, not runtime migration
safety; uncertain changes report `undetermined`.

### Reference a pinned dependency

A dependency shares published definitions without copying them. This optional branch
uses the catalog's approved component definition from `published`, not a live draft.

```python
from domain_kernel import (
    DataType,
    ModelKind,
    ConceptReferenceType,
)

from domain_kernel import PinnedDefinitionReference

consumer_model = await project.create_model(
    actor="user:model-editor",
    display_name="Catalog Consumer",
    description="Application definitions that depend on the published component catalog.",
    kind=ModelKind.PROPOSED,
    dependencies=[published.model_version],
)
published_component = [d for d in published.content.definitions if d.id == component_id][0]
component_reference = PinnedDefinitionReference(
    model=published.model_version,
    definition_id=published_component.id,
    definition_revision=published_component.revision,
)
reference_attribute = AttributeDefinition(
    display_name="component",
    value_type=ConceptReferenceType(concept=component_reference),
    required=True,
)
```

Bare `DefinitionId` references are always local. Qualified references are accepted
by relationship endpoints, reference attributes, activity inputs/outputs/decisions and
business-decision inputs/outputs. Process-local node/role/condition IDs are generated nominal IDs; condition input
symbols and decision input/output keys remain owner-local strings. Only exact declared same-project dependencies are valid, and the
compiler materializes their bundles. Selecting different dependency pins uses a
reviewed dependency-change plan; baseline copying preserves its dependency pins
and never upgrades them implicitly.

```python
from domain_kernel import DataType, EventKind

from domain_kernel import (
    Activity,
    BusinessDecisionDefinition,
    Condition,
    DecisionInput,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    Event,
    Flow,
    DomainModelBuilder,
    Role,
)

model = await project.get_model(name=model.info.name)
component = await model.get_concept(name="component")

editor = Role(
    display_name="Editor",
    meaning="Maintains catalog entries.",
)
submitted = Event(
    display_name="Entry Submitted",
    kind=EventKind.START,
)
check_entry = Activity(
    display_name="Check Component Entry",
    roles=[editor],
    # These reference the definitions of the information used and produced.
    inputs=[component],
    outputs=[component],
)
checked = Event(
    display_name="Entry Checked",
    kind=EventKind.END,
)

builder = DomainModelBuilder(model_info=model.info)
builder.add_process(
    display_name="Catalog Entry Review",
    meaning="An editor checks a submitted component entry before completion.",
    roles=[editor],
    activities=[check_entry],
    events=[submitted, checked],
    flows=[
        Flow(
            display_name="Begin Check",
            source=submitted,
            target=check_entry,
        ),
        Flow(
            display_name="Complete Check",
            source=check_entry,
            target=checked,
        ),
    ],
)
plan = builder.build_change_plan(
    reason="Describe the responsibilities and steps for reviewing catalog entries.",
)

# Submit the description for review; this does not execute the process.
process_case = await model.propose_change_plan(
    actor="user:model-editor",
    plan=plan,
)

# Conditions share generated IDs with the process API; decision input keys remain strings.
number_present = Condition(
    display_name="Number Present",
    description="Number is present",
    input_ids=["number"],
    expression="number is non-empty",
)
decision_body = BusinessDecisionDefinition(
    inputs=[
        DecisionInput(
            id="number", name="Number", definition_id=component_id, data_type=DataType.STRING
        ),
    ],
    outputs=[
        DecisionOutput(
            id="result", name="Result", definition_id=component_id, data_type=DataType.STRING
        ),
    ],
    conditions=[number_present],
    rules=[
        DecisionRule(
            id="rule:valid",
            condition_ids=[number_present.id],
            output_values=[("result", DecisionValue(value="valid"))],
        ),
    ],
)
```

Process bodies support activities, events, roles, flows, exclusive/parallel gateways,
conditions and exception paths.

Use add_process on the same DomainModelBuilder; it returns a provisional DefinitionId
and creates the ordinary ProcessDefinition. Building, submitting and accepting stay
separate. Generated RoleId/ActivityId/EventId/GatewayId/FlowId/ConditionId values and
resolved display_name/name follow the shared naming contract. Child names are unique
across kinds within one process; collisions fail without suffixes. Reused records
retain their IDs. Shared Condition records also have generated IDs/names in decisions.

Direct roles, flow endpoints and conditions must match explicitly supplied process
children; there is no automatic insertion or cross-process lookup. Activity model
references retain inspected snapshots until the builder captures their revisions in
plan bindings; stored body references remain typed IDs/pins. The same collection,
foreign-snapshot and concurrent-revision guards apply as for relationships.

After acceptance, await model.get_process(name="catalog-entry-review") or supply a
process_id instead; optional revision selects history. The immutable Process view has
direct tuple properties and get_role/get_activity/get_event/get_flow/get_gateway/
get_condition getters by exactly one name or typed child ID, without I/O or a .body
step. Missing children raise ProcessPartNotFoundError; duplicate names/IDs raise
ProcessPartAlreadyExistsError. Generic definition lookup remains kind-neutral.

Bundle/repository decoding restores Process and all exact child IDs/names/typed edges.
Runtime authoring snapshots are excluded from wire bodies; plan bindings persist.
Copy/adoption creates fresh child IDs and remaps child and model edges with their owner, preserving names;
exports must preserve supported structure or report projection limits/blockers.
Update the unreleased schema/mapping drafts together; incompatible released formats
need new versions. No automatic workflow/decision execution or expression evaluation.

Decision bodies describe inputs, outputs, conditions
and tables with scalar literal output values; reference-valued table outputs are
outside the initial subset. Text expressions remain inert descriptions. Missing references, roles,
required conditions or supported obligations block readiness. Full BPMN/DMN
round-trip, arbitrary reasoning and workflow/decision execution are outside scope.

The [supported semantic subset](ARCHITECTURE.md#supported-semantics-and-consumer-contracts)
is normative: typed business shapes, explicit binary relationship bounds, descriptive process/
decision bodies and explicitly supported constraint validators. Preserving RDF source
statements does not imply OWL reasoning or ontology round-trip support. Unsupported
mapping/validation constructs produce `Issue` diagnostics with codes and paths;
unsupported required semantics block readiness. Optional unmapped semantics remain
visible limitations. Consumer adapters declare their supported subset and report
unsupported constructs before activation; ERP invariants still require executable
bindings to operational records and transactions.

### Author business shapes, terminology and model checks

The [business-shape contract](ARCHITECTURE.md#business-data-shapes-and-terminology)
uses generated nominal attribute/key IDs, stable names and display names. A type
union replaces primitive `data_type`/`concept_id` combinations. Attributes use
`required`, `collection`, `min_items` and `max_items` as their only presence/collection
representation. Defaults remain optional, single-valued and non-null. `SINGLE` requires
`None` item bounds; `SET`/`LIST` normalize omitted/`None` minimum to `Count(value=0)`
and use `None` maximum for unbounded size. Finite maxima must be at least the minimum.
Bounds apply only to present collections: required empty collections and optional
nonempty collections are distinct supported shapes. Collections/items remain non-null;
nullable single values are independent of presence. `RelationshipCardinality` retains
both directions' `CardinalityBounds`, without changing relationship participation. The primitive payload is supplied only when constructing
its corresponding value object, such as `Count(value=5)`.

Here `manufacturing_model` is the application's own model. The recipe creates a
reusable local unit without an ontology. Optional `add_unit(ontology_term=...)` and
`add_quantity(quantity_kind=...)` references must come from explicitly supplied,
materialized resources; no term lookup, download or implicit adoption occurs.

```python
from domain_kernel import (
    AcceptanceCheckDefinition,
    Accept,
    AttributeDefinition,
    BusinessCode,
    CardinalityBounds,
    CheckRequirement,
    Count,
    DistinctDefinitionsCheck,
    DomainModelBuilder,
    KeyDefinition,
    LabelText,
    LanguageTag,
    LocalizedLabel,
    MeaningText,
    PublicationBlockedError,
    QuantityRequiredCheck,
    RelationshipCardinality,
    StructuredValueType,
    Terminology,
    ValueSetMember,
    ValueSetMembership,
)

manufacturing_model = await project.get_model(name=manufacturing_model.info.name)
builder = DomainModelBuilder(model_info=manufacturing_model.info)
site = builder.add_concept(display_name="Site", meaning="A physical operating location.")
machine_type = builder.add_concept(
    display_name="Machine Type",
    name="machine-type",
    meaning="A manufacturer product model.",
)
site_attribute = AttributeDefinition.reference(
    display_name="Site",
    required=True,
    target=site,
)
asset_code = AttributeDefinition.string(
    display_name="Asset code",
    required=True,
)
machine = builder.add_concept(
    display_name="Machine",
    meaning="An individual physical production asset.",
    terminology=Terminology(
        labels=[
            LocalizedLabel(text=LabelText(value="Machine"), language=LanguageTag(value="en")),
            LocalizedLabel(text=LabelText(value="Stroj"), language=LanguageTag(value="cs")),
        ]
    ),
    attributes=[site_attribute, asset_code],
    keys=[
        KeyDefinition(
            display_name="Site asset identity",
            attributes=[site_attribute.id, asset_code.id],
        ),
    ],
)
status = builder.add_value_set(
    display_name="MaintenanceStatus",
    meaning="The allowed maintenance work-order states.",
    membership=ValueSetMembership.CLOSED,
    members=[
        ValueSetMember(
            code=BusinessCode(value="planned"),
            label=LabelText(value="Planned"),
            meaning=MeaningText(value="Scheduled but not started."),
        ),
        ValueSetMember(
            code=BusinessCode(value="active"),
            label=LabelText(value="Active"),
            meaning=MeaningText(value="Work is in progress."),
        ),
        ValueSetMember(
            code=BusinessCode(value="completed"),
            label=LabelText(value="Completed"),
            meaning=MeaningText(value="The assigned work has finished."),
        ),
    ],
)
bar_id = builder.add_unit(
    display_name="Bar",
    meaning="The bar pressure unit used in our maintenance measurements.",
    symbol="bar",
)
pressure_units = builder.add_value_set(
    display_name="PressureUnits",
    meaning="The reviewed pressure units allowed in this model.",
    membership=ValueSetMembership.CLOSED,
    members=[
        ValueSetMember(
            code=BusinessCode(value="bar"),
            label=LabelText(value="bar"),
            meaning=MeaningText(value="A pressure measurement expressed in bar."),
            unit=bar_id,
        ),
    ],
)
pressure = builder.add_quantity(
    display_name="Pressure",
    meaning="A pressure magnitude expressed in a declared unit.",
    units=pressure_units,
)
measurement = builder.add_concept(
    display_name="Measurement",
    meaning="An individually identified maintenance observation.",
    attributes=[
        AttributeDefinition(
            display_name="Pressure",
            value_type=StructuredValueType(structure=pressure),
            required=True,
        ),
    ],
)
work_order = builder.add_concept(
    display_name="WorkOrder",
    meaning="An instruction to perform maintenance work.",
    attributes=[
        AttributeDefinition.value_set(
            display_name="Status",
            value_set=status,
            required=True,
        ),
    ],
)
builder.add_relationship(
    display_name="Records measurements",
    meaning="A work order records one to five observations.",
    source=work_order,
    target=measurement,
    cardinality=RelationshipCardinality(
        outgoing=CardinalityBounds(minimum=Count(value=1), maximum=Count(value=5)),
        incoming=CardinalityBounds(minimum=Count(value=1), maximum=Count(value=1)),
    ),
)
builder.add_definition(
    display_name="Asset identity check",
    meaning="Keep physical assets and product models distinct.",
    body=AcceptanceCheckDefinition(
        statement=MeaningText(
            value="Machine and MachineType must retain distinct model identities."
        ),
        requirement=CheckRequirement.REQUIRED,
        predicate=DistinctDefinitionsCheck(left=machine, right=machine_type),
    ),
)
builder.add_definition(
    display_name="Pressure binding check",
    meaning="Measurements must retain their declared quantity binding.",
    body=AcceptanceCheckDefinition(
        statement=MeaningText(value="Pressure must bind its magnitude and permitted units."),
        requirement=CheckRequirement.REQUIRED,
        predicate=QuantityRequiredCheck(structure=pressure),
    ),
)
plan = builder.build_change_plan(
    reason="Model reviewed meanings and business data contracts from the manuals."
)

case = await manufacturing_model.propose_change_plan(actor="user:model-editor", plan=plan)
accept = Accept(reason="Reviewed the proposed meanings, fields, translations and checks.")
impact = await manufacturing_model.preview_changes(case=case, decision=accept)
# After the reviewer inspects case.definitions and impact:
await manufacturing_model.decide_review(case=case, decision=accept, actor="user:maintenance-owner")
try:
    prepared = await manufacturing_model.prepare_publication(actor="user:model-editor")
except PublicationBlockedError as error:
    prepared = error.publication
# Inspect prepared.validation.acceptance and prepared.blockers.
```

Preparation raises if required checks fail; publication still rechecks the
stored snapshot and current state. This creates no actual machines, measurements or
work orders. A required `ManualCriterion` yields UNKNOWN
and blocks publication; an advisory criterion remains visible. Editing the statement
or accepting its definition does not record successful execution. Built-in checks
have bounded meanings, and custom validators remain explicit optional bindings.

The same `[site, asset_code]` key appears as a typed consumer obligation in supported
schema/semantic exports. SET exports carry a typed collection-semantics obligation
where target checks do not fully establish presence, equality and bounds. Exact
string/code sets need no extra obligation in JSON Schema or the supported RDF/SHACL
subset; numeric/date/reference sets and initial LinkML sets retain it. The initial RDF
set mapping rejects required-empty and optional-nonempty shapes because missing and
empty have the same triple representation; an obligation cannot repair that loss. The host must enforce any emitted obligations
across its selected records; ordinary schema validation cannot discharge those checks. Known codes,
localized labels and quantity bindings retain exact identities in bundles and
supported projections. Ordered lists, nullable fields, open code sets and decimal
facets follow the target-specific support/rejection table in the architecture.

### Upgrade dependencies through the existing review flow

`maintenance` already depends on a published shared-assets model. `new_assets` is an
inspected published bundle in the same project; `old_asset_ref` and `new_asset_ref`
are exact `PinnedDefinitionReference` values selected by the caller. They are not
names to resolve by similarity. Include all desired direct pins in `after`, including
unchanged ones; the SDK verifies the complete transitive closure.

```python
from domain_kernel import (
    Accept,
    DomainModelBuilder,
    DependencyChangeRequest,
    DependencyRemapping,
    PublicationBlockedError,
)

maintenance = await project.get_model(name=maintenance.info.name)
upgrade = DomainModelBuilder(model_info=maintenance.info)
upgrade.change_dependencies(
    change=DependencyChangeRequest(
        before=maintenance.info.dependencies,
        after=[new_assets.model_version],
        remappings=[DependencyRemapping(before=old_asset_ref, after=new_asset_ref)],
    )
)
# If needed, upgrade.edit_definition(definition=inspected_local_definition, body=repaired_body).
# Edited bodies must already contain final references; remappings handle untouched owners only.
upgrade_plan = upgrade.build_change_plan(reason="Adopt the reviewed shared-assets release.")

case = await maintenance.propose_change_plan(actor="user:model-editor", plan=upgrade_plan)
decision = Accept(
    reason="Inspected dependency versions, affected definitions and required re-review."
)
impact = await maintenance.preview_changes(case=case, decision=decision)
# Inspect case.dependency_change, impact.definition_changes and impact.blockers.
# After the reviewer inspects the complete prospective state:
await maintenance.decide_review(
    case=case,
    decision=decision,
    actor="user:maintenance-owner",
)
try:
    prepared = await maintenance.prepare_publication(actor="user:model-editor")
except PublicationBlockedError as error:
    prepared = error.publication
# Inspect prepared.validation.acceptance, prepared.checks and prepared.blockers.
```

Local model/definition IDs and earlier publications survive. Pins and local repairs
commit together; stale/invalid changes fail without partial effects. Dependency plans
allow revisions/retirements and explicit remappings only, excluding existing-case
inclusion, plan merging, creation/restoration and mapping corrections initially.
Unresolved targets require inspected repairs, never automatic replacement redirects.
Rejecting this parent follows the same generated-member rule as ordinary plans;
dependency plans have no pre-existing included cases to release. Their generated
members cannot be accepted separately against old pins. The decision retains both historical closures without
mixing them into active dependency resolution. Applications separately activate
new versions, migrate ERP records or rebuild knowledge graphs.

## 9. Exports and incremental changes

```python
from domain_kernel import Iri, JsonSchemaProjectionRequest, RdfProjectionRequest, RdfSyntax

# Select the concept from the exact publication being exported.
component = published.get_concept(name="component")

bundle_artifact = await model.export(
    actor="user:model-editor",
    bundle=published,
    store="artifacts",
    path="models/1.0.0.json",
)
print(f"Bundle saved to {bundle_artifact.store}/{bundle_artifact.key}")

schema_projection = await model.export(
    actor="user:model-editor",
    bundle=published,
    store="artifacts",
    path="models/1.0.0.schema.json",
    request=JsonSchemaProjectionRequest(
        root=component, base_iri=Iri(value="https://example.org/domains/")
    ),
)
ontology = await model.export(
    actor="user:model-editor",
    bundle=published,
    store="artifacts",
    path="models/1.0.0.ttl",
    request=RdfProjectionRequest(
        base_iri=Iri(value="https://example.org/domains/"),
        syntax=RdfSyntax.TURTLE,
    ),
)
linked_data = await model.export(
    actor="user:model-editor",
    bundle=published,
    store="artifacts",
    path="models/1.0.0.jsonld",
    request=RdfProjectionRequest(
        base_iri=Iri(value="https://example.org/domains/"),
        syntax=RdfSyntax.JSONLD,
    ),
)
print(f"Schema saved to {schema_projection.store}/{schema_projection.key}")
for limitation in schema_projection.projection_limits:
    print(f"Projection limitation: {limitation}")
# Inspect schema_projection.consumer_obligations for downstream validation duties.
```

Incorporate updated evidence as a new revision of the existing source, then inspect
discovery failures and pending cases before deciding what changes to accept:

```python
from domain_kernel import CaseStatus, Excel

catalog = await project.get_source(name="components")

# Add a revision to the existing source, preserving its identity.
updated_source = await project.ingest_source_revision(
    actor="user:model-editor",
    source_id=catalog.id,
    source=Excel(path="components-updated.xlsx"),
)

update_run = await model.discover(
    actor="user:model-editor",
    sources=[updated_source.revision],
)

print(f"Discovery status: {update_run.status.value}")

for failure in update_run.failures:
    print(
        f"{failure.source_label}: {failure.message} "
        f"[code={failure.code}, retryable={failure.retryable}]"
    )

# Discovery proposes changes; these cases still require review.
pending = await model.list_review_cases(
    run_id=update_run.id,
    status=CaseStatus.PENDING,
)

for case in pending.items:
    print(f"Case {case.id.value}: {case.kind.value}")
    print(f"  Reason: {case.reason}")
    if case.question is not None:
        print(f"  Question: {case.question.text}")

if pending.next_cursor is not None:
    print("More review cases are available.")
    # Fetch the next page with the same filters and cursor=pending.next_cursor.
```

Inspect failures independently of the queue, and continue through any remaining
pages with the same filters. An empty page does not prove discovery succeeded or
review is complete. After reviewing and deciding the cases, compile again to compare
reviewed content with the earlier publication and inspect definition history:

```python
# Compile reviewed content. Pending proposals are not applied.
updated_candidate = await model.compile(actor="user:model-editor")

changes = await model.diff(
    before=published,
    after=updated_candidate,
)

print(f"Compatibility: {changes.compatibility.value}")

for change in changes.changes:
    before_names = [definition.name for definition in change.before]
    after_names = [definition.name for definition in change.after]
    print(f"{change.kind.value}: {before_names} -> {after_names}")

# Use the published concept's stable identity to retrieve its revision history.
component = published.get_concept(name="component")

definition_history = await model.get_definition_history(
    definition_id=component.id,
)

for revision in definition_history.items:
    print(f"Revision {revision.revision}: {revision.display_name} [{revision.status.value}]")
    print(f"  Meaning: {revision.meaning}")

if definition_history.next_cursor is not None:
    print("More definition history is available.")
    # Continue with the same definition_id and cursor=definition_history.next_cursor.
```

Compatible mappings may be reused; changed or uncertain meanings require review.
The diff does not inspect unresolved proposals or establish publication readiness.
After review, prepare and publish a new immutable version; `published` remains unchanged.

Omitting `request` (or passing `None`) writes the complete bundle JSON; its bytes match `bundle.serialize()`. `model.export()` accepts `JsonSchemaProjectionRequest` or `RdfProjectionRequest` for stored projections. The request determines the format, independently of the destination suffix. LinkML retains the pure `project_linkml()` path described below.

The supplied bundle must match the exact stored publication in the bound model by scope, identity and content hash. Export never uses the current draft or substitutes the latest version. The model supplies configured storage and actor-attributed audit; immutable artifact identity and retry guarantees remain in effect.

`JsonSchemaProjectionRequest.root` accepts a concept or structured-value definition,
a local `DefinitionId`, or a `PinnedDefinitionReference`. Direct objects must match
an active local bundle entry by scope, ID, revision and complete content; dependency
roots require explicit pins. Assessment/export reject foreign, absent, removed,
wrong-kind or modified snapshots before artifact writes. They normalize valid inputs
to exact pinned references before report hashing, export journaling and rendering,
so equivalent object/reference requests share projection identity and retry semantics.
Manifests retain references, not embedded definition objects; no wire/mapping change
or live lookup is introduced. `base_iri` supplies stable generated resource identifiers.

JSON Schema and RDF/JSON-LD exports are supported projections with explicit limits;
only the optional LinkML projection supplies YAML/JSON schemas for its explicit subset;
no arbitrary ontology-to-schema equivalence or generic YAML bundle is promised. Schema,
semantic-mapping, reference pack and company-model versions are independent. Export failure
does not undo publication; immutable artifact writes reject different content.
Projection omissions appear in `Artifact.projection_limits`; an essential identity or
required construct without a supported representation causes `ProjectionBlockedError`,
an `UnsupportedCapabilityError` subclass with the full report in `error.assessment`.
Version-qualified identities must not be silently flattened. Consumers derive their
own runtime configurations and explicitly pin model versions.
SDK persistence layouts and internal database schemas are not integration contracts.

### Assess compatibility before export

Use the same [typed assessment](ARCHITECTURE.md#assess-a-projection-before-exporting)
for all projection targets. This recipe looks up `component` in the published catalog
bundle. A root/selection always includes its required reference closure; it cannot
discard applicable semantics to force success.

```python
from domain_kernel import (
    Iri,
    JsonSchemaProjectionRequest,
    LinkmlProjectionRequest,
    RdfProjectionRequest,
)

component = published.get_concept(name="component")
request = JsonSchemaProjectionRequest(
    root=component, base_iri=Iri(value="https://example.org/domains/")
)
report = published.assess_projection(request=request)
```

The returned `ProjectionAssessment` exposes `report.availability`, `report.exportable`,
`report.findings` and `report.consumer_obligations`. Inspect the typed locations,
feature results, remedies and obligations before export.
Representation (native, annotated or unsupported) is independent of validation
responsibility (target, host, not applicable or unsupported). Host obligations permit
serialization but must be fulfilled for instance conformance. Missing optional
adapters, unknown mappings or failed analysis are explicit non-exportable outcomes;
invalid bundle/request inputs raise the existing errors. Explicit assessment is optional;
export always assesses internally and raises before writing if blocked. Reuse the
same request and exact source publication:

```python
schema = await model.export(
    actor="user:model-editor",
    bundle=published,
    request=request,
    store="artifacts",
    path="models/catalog.schema.json",
)

rdf_report = published.assess_projection(
    request=RdfProjectionRequest(base_iri=Iri(value="https://example.org/domains/")),
)
linkml_report = published.assess_projection(
    request=LinkmlProjectionRequest(
        base_iri=Iri(value="https://example.org/domains/"), definition_ids=[component.id]
    ),
)
```

RDF assessment covers all four roles plus dependencies, including when `Model.export`
later selects one role. LinkML selection includes its required closure. Reports are
read-only, require no producer database and never authorize publication or mutate
models. Serialization reruns the same target analysis and preserves the assessed
obligations; there is no separate capability registry or stale-report bypass.

A review UI can catch the failure and display the same typed assessment:

```python
from domain_kernel import ProjectionBlockedError

try:
    schema = await model.export(
        actor="user:model-editor",
        bundle=published,
        request=request,
        store="artifacts",
        path="models/catalog.schema.json",
    )
except ProjectionBlockedError as error:
    blocked_assessment = error.assessment
    # Display availability, findings, consumer_obligations, issues and next_steps.
```

The error covers every non-exportable assessment, including missing projection
adapters, unknown mappings and failed analysis. No artifact is written. Invalid
input, scope, authentication and storage failures retain their own typed errors;
they do not fabricate an assessment. This error does not create a persisted
publication-preparation snapshot or undo the original publication.

Exact string/code sets need no `CollectionSemanticsObligation` when JSON Schema
bounds/uniqueness or RDF/SHACL datatype/count checks fully enforce their semantics.
Equality is exact and case-sensitive, without trimming or normalization. Numeric,
date/datetime and reference sets conservatively retain host equality/count checks;
initial LinkML set mappings retain them too. This does not remove keys, reference
resolution or cross-record relationship obligations. Duplicate typed values are
rejected, not silently deduplicated.

Static open value sets map to permissive LinkML string types, with versioned
`dk:open_value_set` annotations using `OpenValueSetAnnotation` and the existing
`ValueSetDefinition` body. Ordinary tools may ignore the known-code catalog; they
must still allow unlisted strings. SDK import validates the version, source pins and
body, rejects conflicting narrowed ranges/copies, and returns new proposed identities.
Missing annotations yield ordinary strings, not inferred vocabularies. Original-term
resources must exist in the destination model before submission; import does not
fetch/adopt them. Source pins retain provenance, not authenticity or merge authority.
Dynamic vocabularies and unknown annotation dialects remain unsupported.

### Standards projections and LinkML import

The [architecture mapping contract](ARCHITECTURE.md#standards-mappings-and-optional-schema-tooling)
is authoritative. These operations use the published typed model as input; neither
an RDF graph nor a LinkML schema becomes a second editable workspace. No producer
`Client` or database is needed for standalone projection.

RDFLib may construct temporary in-memory graphs for validation and serialization;
this does not change the SDK's persistence contract. In the manufacturing example,
the ontology describes the `Machine` class, while instance shapes describe valid
machine records. The GraphRAG host separately extracts and resolves `Press-17` and
its facts, validates its own instance graph, and controls graph-database ingestion.

```python
from domain_kernel import Iri, RdfSyntax, SemanticGraphRole, project_semantics

semantic = project_semantics(
    bundle=loaded,
    base_iri=Iri(value="https://example.org/domains/"),
    syntax=RdfSyntax.TURTLE,
)
# Inspect semantic.model, semantic.mapping, semantic.identities and semantic.issues.
ontology_documents = [
    document for document in semantic.documents if document.role == SemanticGraphRole.ONTOLOGY
]
instance_shapes = [
    document
    for document in semantic.documents
    if document.role == SemanticGraphRole.INSTANCE_SHAPES
]
# The host transports payload bytes and uses each document.graph_iri as its target graph.
# Documents include the exact materialized dependency closure; no live ontology lookup.
```

Use a caller-controlled stable base IRI. Names/aliases never determine external
identity. The manifest preserves source pins, exact output hashes, term-to-definition
bindings and mapping/library versions. Four graph roles separate the ontology,
model metadata, model validation shapes and instance shapes. Turtle/JSON-LD encode
the same mapped graph content; graph names remain explicit in the manifest.

RDFS declares types/properties; SHACL describes validation. Attributes preserve independent presence, collection kind and item bounds;
unsupported list projections fail. Relationships carry explicit forward/inverse
minimum and maximum counts. The named relationship factories default minima to zero,
while explicitly supplied bounds can require participation. `ConstraintTarget.MODEL`
is the default; `INSTANCE` explicitly describes business-record constraints.
Preparation validates model-target rules and the syntax/supported subset of instance
targets. It does not validate the application's records or implement ERP transactions.
The host selects a published version and runs/binds its own data checks.

JSON Schema separates object `required` from present-array `minItems`/`maxItems`.
RDF singles use minCount from `required` and maxCount 1. RDF sets support optional
minimum-zero or required positive-minimum fields only; other presence combinations
fail preflight/export. LinkML maps presence and multivalued size bounds independently;
its collection obligation requires hosts to preserve missing/empty distinctions and
validate presence, size and equality before normalization. Imports never infer
requiredness from positive item counts. Complete bundles preserve every combination.

For example, an explicitly required string `Machine.asset_code` generates an instance
shape requiring exactly one string value. Model preparation checks that shape's
supported definition; it does not check whether a downstream `Press-17` record has an
asset code. Exporting shapes neither runs that downstream check nor installs database
constraints. RDF interchange, SHACL validation and optional LinkML schema tooling are
separate capabilities; consumers select the ones their workloads need.

An existing artifact store can receive one semantic graph through the typed export
variant. The RDF request carries identity and syntax; `role` defaults to `ONTOLOGY`
and is valid only with an RDF request. Assessment still covers all four roles. `Artifact.semantic` records
the source model pin, graph IRI, role and mapping version for the exported document:

```python
from domain_kernel import Iri, RdfProjectionRequest, SemanticGraphRole

shape_artifact = await model.export(
    actor="user:model-editor",
    bundle=published,
    store="artifacts",
    path="models/catalog.instance-shapes.ttl",
    request=RdfProjectionRequest(base_iri=Iri(value="https://example.org/domains/")),
    role=SemanticGraphRole.INSTANCE_SHAPES,
)
```

For a data-schema workload, explicitly project selected content through the optional
`linkml` adapter. `definition_ids=None` selects every active root-model definition;
an explicit selection includes its reference closure and pinned dependencies and
records exclusions. Unsupported selected structures cause a diagnostic failure.

```python
from domain_kernel import Iri, LinkmlSyntax, project_linkml

schema_projection = project_linkml(
    bundle=published,
    base_iri=Iri(value="https://example.org/domains/"),
    definition_ids=[component_id],
    syntax=LinkmlSyntax.YAML,
)
# Inspect schema_projection.selected, schema_projection.excluded_definition_ids and
# schema_projection.issues.
schema_document = schema_projection.schema
# Hand schema_document.payload plus its materialized dependencies to approved host tooling.
```

The supported mapping covers flat classes, structured inlined values, static closed
code sets, annotated static open value sets, scalar/reference/set attributes, explicit
bounds, declared keys and paired binary relationship slots. Ordered/nullable/dynamic-enum/faceted-decimal constructs
follow the architecture's explicit rejection table. No implicit inheritance flattening
or conversion of unsupported rules, processes or decision tables occurs. LinkML's own generators can help the host produce Python/Pydantic
models, JSON Schema, SQL DDL and documentation; the SDK promises the declared schema
mapping, not all generator outputs or operational correctness.

Selecting definitions does not permit omitting their applicable semantic links,
inherited constraints or adopted formal axioms. Unsupported selected semantics fail;
produce an explicitly reviewed derived model when a simpler schema is intended.

A supplied LinkML schema can become a **new authoring plan**. The document and its
supplied dependencies carry exact byte hashes. This branch imports the previous
projection into a separate model; it does not silently merge with the original.

```python
from domain_kernel import ModelKind, load_linkml

import_model = await project.create_model(
    actor="user:model-editor",
    display_name="Schema Derived",
    description="Component catalog definitions proposed from supplied schemas for application review.",
    kind=ModelKind.PROPOSED,
)
import_result = load_linkml(
    document=schema_projection.schema,
    dependencies=schema_projection.dependencies,
    model_info=import_model.info,
    reason="Review the supplied schema's meanings for this application.",
)
# Inspect import_result.issues and import_result.origins.
if import_result.plan is not None:
    import_case = await import_model.propose_change_plan(
        actor="user:model-editor", plan=import_result.plan
    )
# Preview and explicitly decide; import never grants approval or creates pack obligations.
```

Imported definitions retain schema/element origins and start as hypotheses under new
local IDs. Mapping errors return issues with no usable plan; malformed/hash-invalid
inputs raise `InvalidSchemaError`. Only supplied hash-verified dependencies and pinned
packaged `linkml:types` are resolved. Envelope schema IRIs must match parsed IDs;
CURIEs/imports resolve through declared prefixes to exact supplied absolute IRIs.
Conflicting imported element keys/IRIs or prefixes and import cycles are rejected
before library overlays; no path/suffix fallback is allowed. Byte/nesting limits apply, and no external fetch,
code execution or implicit schema installation occurs. Reuse the same returned plan
for retries; a fresh import is a new proposal, not inferred identity reconciliation.

RDFLib/pySHACL (`ontology`) and LinkML (`linkml`) are optional adapter dependencies,
loaded only when used. Builders, normal review, typed bundle consumption and core
validation remain available without them. Graph databases, generated application
code, UI rendering, data migrations and operational validation runs remain host-owned.

Reusable units use the normal definition naming, review and edit/remove/restore lifecycle.

```python
manufacturing_model = await project.get_model(name=manufacturing_model.info.name)
bar = await manufacturing_model.get_unit(name="bar")
unit_builder = DomainModelBuilder(model_info=manufacturing_model.info)
unit_builder.edit_unit(
    unit=bar,
    meaning="The bar pressure unit used for declared maintenance measurements.",
)
unit_plan = unit_builder.build_change_plan(reason="Clarify the shared pressure unit.")
# Submit and review unit_plan separately; building it does not change the model.
```

`edit_unit()`, `remove_unit()` and `restore_unit()` preserve inspected identity and
revision guards through the same generic plan operations. Omitted fields use `UNSET`;
explicit `None` clears optional symbol/ontology references. No conversion is inferred.
A member's `unit` must resolve to an active `UnitDefinition`; do not also supply
`ontology_term` on that member. Both fields may be absent for local inline units.
Closed unit sets, required non-null magnitude/unit fields, and typed reference guards
remain mandatory; `QuantityRequiredCheck` accepts a valid binding with no external kind.
Unit edges participate in pack composition, dependency closure, baselines, slices and imports.

Complete bundles preserve unit bodies/metadata, member references and explicit nullable
quantity kinds. JSON Schema keeps operational unit codes in enums and records typed
`UnitAnnotation`/`UnitBindingAnnotation` metadata in `x-domain-kernel`. RDF emits labelled
local unit resources and exact code bindings while retaining string-valued unit shapes;
optional ontology references never imply equivalence or imports. LinkML keeps the same
codes, maps reusable units to local meaning IRIs, and carries complete unit/binding
records in versioned annotations, including standalone selected units. Import creates
fresh IDs and remaps all edges; unknown, incomplete or contradictory annotations fail.
These additions extend the unreleased 1.0 wire/mapping drafts together; released contracts
require new versions for incompatible changes. Unsupported exporters must report blockers,
not omit units or claim dimensional validation or conversion.

### Original ontology terms, formal modules and reasoning

Use `load_ontology` for explicitly supplied formal semantic resources. `OntologyDocument`
contains bytes and an exact hash plus document/ontology/version identities and a
selected ontology graph; application readers perform acquisition. A missing graph
selector means the default graph only. Other named graphs are preserved, not unioned.
Embedded bytes use the shared strict base64 wire contract; structural bundle loading
verifies hashes without starting parsers or reasoners. Its optional adapter defaults to lazy RDFLib for supported
RDF syntaxes. OWL/XML, Functional or Manchester syntax requires an adapter advertising
that syntax. Parsing and preservation do not themselves perform reasoning.

This example assumes a supplied equipment document defining the `Pump` class and all
its imports/contexts. A missing dependency, changed hash, ambiguous alias or unsupported
parser fails; it does not fall back to a web download.

```python
from domain_kernel import (
    Accept,
    DomainModelBuilder,
    Iri,
    ModelTermReference,
    OntologyEntityKind,
    OntologyModuleDefinition,
    OntologyTermReference,
    SemanticLinkDefinition,
    SemanticRelation,
    load_ontology,
)

equipment = load_ontology(document=equipment_document, resources=equipment_resources)
pump_term = OntologyTermReference(
    source=equipment.root,
    term_iri=Iri(value="https://example.org/equipment/Pump"),
    entity_kind=OntologyEntityKind.CLASS,
)
model = await project.get_model(name=model.info.name)
authoring = DomainModelBuilder(model_info=model.info)
authoring.add_definition(
    display_name="Equipment ontology module",
    meaning="The selected formal equipment vocabulary.",
    body=OntologyModuleDefinition(ontology=equipment),
)
industrial_pump_id = authoring.add_concept(
    display_name="Industrial Pump", meaning="A physical pump used in industrial production."
)
authoring.add_definition(
    display_name="Industrial pump specialization",
    meaning="Every industrial pump is a pump under the selected equipment definition.",
    body=SemanticLinkDefinition(
        subject=ModelTermReference(
            definition=industrial_pump_id,
            entity_kind=OntologyEntityKind.CLASS,
        ),
        relation=SemanticRelation.SUBCLASS_OF,
        object=pump_term,
    ),
)
plan = authoring.build_change_plan(reason="Adopt reviewed equipment semantics.")

case = await model.propose_change_plan(actor="user:model-editor", plan=plan)
acceptance = Accept(reason="Inspected the module, source version and formal specialization.")
impact = await model.preview_changes(case=case, decision=acceptance)
# After the reviewer inspects the members and impact:
await model.decide_review(
    case=case,
    decision=acceptance,
    actor="user:domain-owner",
)
```

For reusable reference assets, set `ReferenceDefinition.ontology_terms` and supply
the corresponding closures through `ReferencePackSpec.ontologies`. Composition retains
external IRIs and kinds while namespacing only SDK reference IDs. Matching names do
not merge definitions. A provenance binding does not adopt the entire ontology;
reviewed modules explicitly adopt logical closures. A formal link asserts its stated
relationship but does not import all source axioms; documentation links never do.

OWL import cycles are permitted and traversed once per pin. This differs from SDK
model dependencies and the initial LinkML import contract, which reject cycles.
Subclasses may have multiple parents or form equivalence cycles. Formal subclass
links never mean part-of or automatically copy fields into ERP records. Business
`NARROWER`/`EQUIVALENT` alignments remain separate from formal RDFS/OWL/SKOS assertions.

Optional reasoning always names the task, standard language profile and semantics.
The caller supplies an adapter with matching capabilities; an enum value does not
promise that an installed engine supports it. Here `owl_reasoner` is host supplied.

```python
from domain_kernel import (
    ReasoningProfile,
    ReasoningRequest,
    ReasoningTask,
    SemanticRegime,
    reason_ontology,
)

reasoning = await reason_ontology(
    ontology=equipment,
    reasoner=owl_reasoner,
    request=ReasoningRequest(
        profile=ReasoningProfile.OWL2_DL,
        regime=SemanticRegime.OWL_DIRECT,
        task=ReasoningTask.CONSISTENCY,
    ),
)
# Inspect reasoning.status, reasoning.consistent and reasoning.issues.
```

`ReasoningResult` preserves exact inputs, adapter/version, request, status and derived
statements separately. Unknown/incomplete/unsupported/timeout is not a successful
logical check. Consistency is distinct from class satisfiability and data validation.
OWL's open-world cardinality does not enforce a required stored field; use selected
SHACL instance checks for that data-contract requirement.

To require reasoning during preparation, inject a `ReasoningModelValidator` through
`ClientIntegrations.validators`. It receives the shared projector, reasoner and
request, fingerprints them and records its candidate-bound report in
`ValidationReport.reasoning`. Additional validators never replace core checks.
The initial preparation validator accepts consistency or classification of all named
classes, rejecting scoped signatures/queries and entailment tasks at construction.
Candidate-local IRIs do not exist when configuring it. Standalone reasoning retains
scoped and entailment operations on known immutable inputs. Consistency must be true;
classification also requires no unsatisfiable named classes. Unsupported or incomplete
required checks block publication. Reports belong to publication/bundle hashes, not
their input candidate hash. Inference never changes approved definitions or record identity.

### Compose domain models and select a workflow view

Model maintenance, procurement and production independently when their meanings or
ownership differ. A small shared model can supply agreed definitions. A reviewed
integration model pins the domains it connects. A workflow usually consumes a slice;
create a separate workflow model only when it owns additional meanings or a lifecycle.

```python
from domain_kernel import PinnedDefinitionReference, TraversalDirection, compose_models, slice_model

enterprise = compose_models(
    bundles=[maintenance_bundle, procurement_bundle, production_bundle, integration_bundle],
)
repair_view = slice_model(
    composition=enterprise,
    seeds=[
        PinnedDefinitionReference(
            model=maintenance_bundle.model_version,
            definition_id=work_order_definition.id,
            definition_revision=work_order_definition.revision,
        ),
    ],
    max_hops=1,
    direction=TraversalDirection.BOTH,
)
# Inspect repair_view.selected, repair_view.support and repair_view.models.
```

Only verified published versions in one project can compose. Exact dependencies are
included; conflicting versions or scopes fail. A composition neither merges meanings
nor creates a new approval. Slicing preserves qualified identity and closes required
references, including materialized ontology resources. Size limits fail rather than
silently truncating support. Hosts authorize the complete slice before exposing it;
it is not a permissions boundary. Edits return to each definition's owning model.

For a formal ontology subset, use the separate `extract_ontology_module` operation
with an explicit extractor, method, semantic profile/regime, seed terms and new ontology
IRI. The report records exact limits and a reproducible fingerprint. BOT/TOP/STAR
locality methods declare a signature-specific guarantee; MIREOT and ordinary graph
neighborhoods do not promise preservation of logical entailments. Inspect status,
guarantee and diagnostics before proposing the returned module for review.

<a id="10-optional-notebook-inspection-and-testing"></a>

## 10. Notebook journey, inspection and testing

The notebook is the primary hands-on guide and human exploratory/product-acceptance
environment, alongside unit and integration tests. The canonical
[developer journey](ARCHITECTURE.md#the-legislative-domain-model-notebook-journey) begins
with the first implemented manual-model lifecycle and expands with the SDK. Notebook
dependencies remain optional at runtime; ordinary model methods are identical in
notebooks and backend code.

The initial [interactive preview](examples/notebooks/README.md) may execute labelled
fixtures beside commented planned calls for the complete journey, including advanced
exercises and quantities. Canonical snapshots remain immutable; optional experiments
are isolated and require explicit actions. Keep preview and SDK implementation status
separate in the coverage ledger. Replace fixtures per owning issue without changing
cell identities; simulated results never satisfy the real-SDK acceptance criteria.
Local teaching exercises must preserve answers on cell reruns, invalidate stale feedback
after edits, and provide static worked answers. Their feedback is separate from SDK validation
and must never mutate the canonical model or submit review decisions.

Use one continuous developer story: a lobbying organisation needs a reusable model
for its legislative-analysis application serving employment-sector clients. Start
with a manually authored recruitment-system/provider/deployer seed, then parse real documents,
discover and reconcile meanings, refine data shapes, review, publish, export and
evolve the model. Legislative intelligence, client-specific analysis and operational
records belong to the consuming application; the tour ends at independent model
consumption rather than building that application.

The 60–90 minute core tutorial must explain motivation, interpretation, experiments
and transitions in connected second-person prose. Its expanded model covers intended
purpose, recruitment entities, responsibilities, documentation, data/safeguards and
legislative context. Keep general AI systems separate from the recruitment-scoped
seed. Instructions for use is the principal cross-format shape; preserve Article 6
qualifications and Article 26(6) control, duration and exception conditions as
descriptive semantics, without classifying actual organisations or converting months
to fixed days. Human confirmation and structural validation remain separate.

Shared example-only records must drive snapshot membership, counts, views, mappings,
review history and publication differences. Validate evidence references and curated
export excerpts; show direct support, inferred structure and authored choices in
inspection views. Focused diagrams have explicit view counts and a complete inventory.
Retain immutable prior publications and pending/accepted separation. Guard the core
distinctions with regression cases; use these expectations later for discovery
evaluation, not as evidence of current extraction accuracy.

Show the Article 13 evidence-to-consumption thread as one worked example. The
independent consumer must expose reusable fields and citations alongside remaining
interpretation responsibilities, without fetching sources or deciding compliance.
Keep one primary result visible per chapter, expandable supporting details, and a
directed connection matrix equivalent to each focused diagram.

Use the architecture's [pinned corpus and ontologies](ARCHITECTURE.md#notebook-corpus-and-ontologies):
AI Act passages, Commission AI-system guidance and an employment-sector position
paper, with ELI and DPV/AI Act reference resources; LOMO is an optional advanced
exercise. Retain editions, source locations, languages, hashes and attribution
terms. Distinguish legislation, guidance, stakeholder views and developer-authored
structures. Select DPV's RDFS/SKOS or OWL representation explicitly, preserving its
namespace/semantics; formal adoption remains separate from business mapping.

Follow the [capability coverage map](ARCHITECTURE.md#notebook-capability-coverage)
for the main chapters, linked advanced exercises and specialist recipes. Include
formal links, supported reasoning/module extraction with host-supplied adapters,
pack/pattern composition, model dependencies/views/upgrades, multilingual and rich
shapes, CSV/Excel profiling, host-parsed evidence, attributed clarification,
descriptive processes/decisions, LinkML import, projection diagnostics and recovery.
Keep units/numeric detail and deployment/conformance cases in focused recipes where
they do not fit the main story. Each capability records an executable location,
fixture pins, prerequisites, expected outcomes, tests and human acceptance evidence;
planned coverage is not a claim of implemented or verified support.

### Inspect loaded values naturally

```python
from domain_kernel import enable_notebook_display

# Enable once per kernel; ordinary value expressions then render captured snapshots.
enable_notebook_display()
publication  # Already loaded through the ordinary SDK; display performs no I/O.
```

Inspect `publication.checks` in a separate cell. Definition cards, bounded pages,
ingestion/discovery outcomes, review cases and impacts, change sets, projection
assessments, bundles and exported artifact metadata have useful views with plain-text
fallbacks. Show captured identity/revision and loaded-page counts; never invent a
total or imply fresh state.
Rendering performs no persistence reads, inference, evidence acquisition, writes or
state transitions. Excerpts require explicitly loaded `EvidenceContent`.
Applications can supply a typed `NotebookRenderer`; `render_notebook()` is a
low-level escaped-HTML inspection utility and `disable_notebook_display()` restores
prior formatters. Importing the SDK does not import IPython.

Optional notebook controls belong to the example application's presentation and
callback code, not the renderer or domain records. They use the same typed public
operations and show the equivalent Python: select, inspect, choose a decision and
reason, preview, then explicitly submit. Keep essential workflows executable from
code cells. Preserve verified actors, exact revisions, stale-state and idempotency
guards; no second review store or hidden automatic acceptance.

### Run and maintain the tour

- Provide a credential-free demo using fixtures from the pinned real corpus,
  separately labelled authored examples/failure cases, actual SDK persistence and
  explicitly labelled replayed inference/pre-parsed evidence. A clean Run All uses
  an isolated workspace and scripted sample actors. Optional live parsing, remote
  sources and gateways declare their prerequisites and do not silently execute.
  Live corpus runs and real-data starters have explicit review/publication gates,
  not an accept-all Run All path.
- Explain new workspace, resume and sample-only reset. A kernel restart does not
  reset SQLite. Retain resource identities and operation/plan keys, distinguish
  retries from new intent, reload after mutations and never suffix duplicate names
  or reset user data. Use top-level `await` and explicit demo configuration/paths.
- Keep one portable `.ipynb` paired with reviewable Jupytext source. Derive the
  executed reading guide from that tested notebook; sanitize saved outputs and
  keep runtime stores and credentials out of Git. Version it with the SDK and map
  every capability to its chapter or linked recipe as implementation grows.
- Target Jupyter Notebook/JupyterLab and VS Code, with an optional prepared
  Codespaces environment. Evaluate Deepnote separately against the same portable
  journey and capability matrix. Widget support is optional; static/text and
  code-cell alternatives remain usable. Test accessible labels, keyboard use,
  tables accompanying graphs and light/dark presentation in advertised frontends.
- Lock notebook tooling with uv, preserving the dependency cooldown and lightweight
  core. Show versions, workspace and capabilities without secrets; avoid hidden
  installation, working-directory or event-loop changes. First use needs no
  heavyweight parser models or provider account after environment provisioning.
- Run the deterministic journey in CI from a fresh kernel without network access,
  with timeouts and unexpected-error failure. Catch intentional teaching failures;
  verify bundle round trips independently. Cover reruns/restarts and state guards,
  with separate browser tests for controls. Human exploratory acceptance uses this
  same journey and feeds improvements back into examples and regression tests.
  Separately evaluate live parsing/discovery against reviewed corpus expectations
  for model quality, citations, mappings and correction effort; replay success is
  not evidence of live extraction quality.

The architecture's [delivery and acceptance contract](ARCHITECTURE.md#portable-delivery-and-continuous-acceptance)
defines platform boundaries, release evidence and the first-publication usability
target. These remain real-SDK requirements; the preview's recorded frontend checks
do not establish implemented SDK behavior or broader platform support.

## 11. Capability and integrity boundaries

Keep common failure messages actionable using the existing exception/code/issue
contracts: identify the allowed resource/path context and an appropriate next step.
Prioritize missing/duplicate names, missing extras, setup failures, stale state and
blocked publication. Bounded same-scope, same-kind spelling suggestions are optional;
omit them when expensive or unavailable. Never change exact lookup, expose other
scopes/secrets, invoke inference or obscure the original error to generate a hint.

```python
# ConfigurationError: invalid types/references/secrets/policies; no partial client.
# ProjectAlreadyExistsError / ModelAlreadyExistsError: retrieve by name or choose a different name.
# MissingCapabilityError: an inference operation has no configured gateway.
# MissingDependencyError: a selected optional adapter is not installed; no fallback.
# UnsupportedBundleVersionError: unregistered wire version; no silent migration.
# InvalidBundleError: invalid wire schema, integrity, references or approval bindings.
# InvalidReferencePackError / UnsupportedReferencePackVersionError: invalid/unsupported pack payload.
# SourceRevisionMismatchError / EvidenceUnavailableError: changed/unavailable exact evidence.
# ScopeMismatchError: object belongs to another project/model outside an explicit pin boundary.
# StaleStateError: workspace/review/policy changed; prepare again with the key omitted or a new key.
# InvalidDecisionError: incompatible action or attempted waiver of a required obligation.
# PublicationBlockedError: inspect blockers; resolve them and prepare with the key omitted or a new key.
# ProjectionBlockedError: inspect error.assessment; resolve projection blockers before exporting.
# Same scope/operation/key + same canonical request -> stored outcome; changed payload -> conflict.
# All list operations are bounded and expose next_cursor.
```

Five slices remain: sources, discovery, reconciliation, review and modeling; each has
`api/`, `application/`, `domain/`, `infrastructure/`. Domain models use stdlib-only
contracts. Pydantic/settings, providers, parsing and persistence stay at boundaries.
Keep implicit slice namespaces, the root public exports and `py.typed`.

Start development with shared records and the ports needed for the manual-modeling
vertical slice, including corrections, coordinated review and independent bundle
loading. Expand toward pack authoring/adoption, reference patterns, baseline comparison
and discovery after that slice works. This inventory does not require building every interface stub first.

**Implementation status:** these contracts remain proposals. No runtime SDK behaviour
is asserted here. `pydantic-settings` is still an undeclared future dependency;
the optional `linkml` extra is also a proposed implementation dependency;
this documentation task adds no dependencies. See [AGENTS.md](AGENTS.md).

## Optional interoperability roadmap

The [architecture roadmap](ARCHITECTURE.md#optional-interoperability-roadmap) is the
source of truth for optional QUDT/UCUM, SSSOM, R2RML/CSVW, industry packs/adapters,
RDFC-1.0, DCAT 3 and wider schema/process/query integrations. They introduce no
required configuration, dependencies or executable API promises in these recipes.
Use the typed quantity/association patterns now; specialized validation, interchange
and downstream execution are separate optional workstreams.

Ordered RDF lists, null-in-RDF, decimal-facet projection and arbitrary OWL-to-schema
conversion remain in the optional mapping roadmap. Static annotated open LinkML sets
are supported in the initial bounded design; dynamic vocabularies remain deferred.
