# Architectural Guarantees, Limitations and Verification

[Architecture overview](../../ARCHITECTURE.md) · [Contract index](README.md)

<a id="12-guarantees-limits-and-reference-map"></a>

This document describes what applications can rely on when using Domain Kernel, how to recover from common failures and how contributors should verify the SDK's architectural guarantees.

The [individual architecture contracts](README.md) define the detailed behaviour of each operation. Shared terminology is defined in the [glossary](../../GLOSSARY.md).

## 1. What a Published Model Guarantees

A published model preserves the definitions, evidence references and decisions that were accepted and authorized at a particular point in time.

Consider a procurement model that distinguishes a supplier's promised delivery date from the actual receipt date recorded by a warehouse.

Domain Kernel can verify that these definitions have distinct identities, that their references resolve correctly and that the model passed its required publication checks. It also preserves the evidence and decisions behind their acceptance.

Whether those definitions accurately describe the business remains a judgment for the reviewer.

| Guarantee | Limitation |
|---|---|
| Required definitions, references and alignments resolve within the declared model scope. | Structural consistency does not establish business correctness. |
| Required supported reference-pack obligations and confirmation checks have passed. | Passing these checks does not establish legal compliance or suitability for a particular business. |
| Release authorization is bound to exact content, state, policy and actor attribution. | The SDK does not authenticate the actor or verify their business authority. |
| Published versions are immutable and their provenance is pinned. | External evidence may become unavailable. |
| Bundle loading verifies structure, hashes and internal bindings. | Loading does not repeat inference, retrieve evidence or automatically migrate unsupported wire formats. |
| Descriptive processes and decisions satisfy their supported structural checks. | Structural validation does not execute processes or prove arbitrary textual conditions. |

Domain Kernel manages the integrity and history of the model. Reviewers determine whether it accurately represents the business, while consuming applications decide how to use and enforce its requirements.

See [review and publication](review-and-publication.md) and [bundles and interoperability](bundles-and-interoperability.md).

<a id="failures-and-the-next-action"></a>

## 2. Failures and Recovery Actions

Documents can become unavailable, inference providers can fail and model state can change while a reviewer is inspecting it.

Domain Kernel reports these conditions explicitly. It does not substitute newer documents, select different resources or apply decisions to state that the reviewer has not inspected.

### Diagnostic requirements

An error message should explain what failed, identify the affected resource or operation within the permitted context, and suggest a useful next action.

Prioritize clear diagnostics for common problems such as missing or duplicate names, unavailable optional dependencies, invalid configuration, incompatible database schemas, stale decisions and blocked publications.

Typed exceptions, diagnostic codes, retryability indicators and structured issue paths remain the programmatic error contracts. Human-readable messages provide guidance without introducing a separate repair API.

Where practical, a failed lookup may include a bounded, deterministic spelling suggestion from the same authorized scope and expected resource kind.

For example, looking up `componnet` might suggest the existing `component` definition. The original lookup must still fail.

Suggestions must not search other scopes, invoke inference, change lookup semantics, retry writes or hide the original failure if suggestion generation fails.

Diagnostics must exclude secrets, raw provider exceptions and private source excerpts.

### Configuration and capabilities

| Error | Recommended action |
|---|---|
| `ConfigurationError` | Correct the reported configuration fields or resource references. |
| `MissingCapabilityError` | Supply the required capability, such as an inference gateway or validator. |
| `MissingDependencyError` | Install the required optional dependency extra. |
| `UnsupportedCapabilityError` | Select a supported operation or semantic mapping. |
| `ReferencePackNotFoundError` | Select an available approved reference-pack version. |
| `AuthenticationError` | Check host-supplied credentials and permissions. |
| `ResourceLimitError` | Reduce the input size or explicitly adjust the applicable limit. |

See [workspace and configuration](workspace-and-configuration.md).

### Resource identities and lookups

Resource creation and retrieval are separate operations. Creating a resource with an existing name does not return the existing resource or generate a different name automatically.

| Error | Recommended action |
|---|---|
| `ProjectAlreadyExistsError`, `ModelAlreadyExistsError`, `SourceAlreadyExistsError`, `DefinitionAlreadyExistsError` | Retrieve the existing resource by `name` or choose an unused name. |
| `DefinitionNotFoundError`, `DefinitionKindMismatchError` | Check the owning model, exact name or ID, and expected definition kind. |
| `AttributeNotFoundError`, `KeyNotFoundError` | Check the owning concept and exact name or ID within the inspected revision. |
| `AttributeAlreadyExistsError`, `KeyAlreadyExistsError` | Choose an unused name within the owning collection. |
| `SourceNotFoundError` | Check the project and exact source identity before ingesting a revision. |
| `ScopeMismatchError` | Use the correct model scope or an explicitly pinned published dependency. |

See [workspace and configuration](workspace-and-configuration.md) for naming, identity and lookup rules.

### Source availability and discovery

An evidence citation identifies the source revision used to establish a particular interpretation.

If a manufacturer replaces an equipment catalog, the updated catalog cannot serve as evidence for a decision based on the original revision. Recover the original content or capture the updated document as a new revision.

| Error or outcome | Recommended action |
|---|---|
| `SourceUnavailableError` | Check the configured reader, source location and access permissions. |
| `SourceRevisionMismatchError` | Recover the exact recorded content or capture changed content using `ingest_source_revision()`. |
| `EvidenceUnavailableError` | Recover the original revision or retained evidence required by the citation. |
| `InferenceError` | Inspect the failure, correct its cause and resume eligible work. |
| Failed or partially failed discovery | Inspect the persisted run and its failures before deciding whether to resume or use the available proposals. |

An incomplete discovery run may still contain useful proposals. Applications should present those proposals alongside the recorded failures.

An empty review queue does not establish that discovery succeeded.

See [sources and evidence](sources-and-evidence.md) and [discovery and reconciliation](discovery-and-reconciliation.md).

### Review and publication

A reviewer may inspect a definition and prepare a decision while another user is modifying the model.

Applying the decision to a newer definition could change what the reviewer intended to approve. The SDK therefore rejects stale decisions rather than silently updating their targets.

| Error | Recommended action |
|---|---|
| `InvalidDecisionError` | Inspect the review case and construct a compatible decision or resolve its outstanding requirements. |
| `StaleStateError` | Reload the current state, inspect the changes and prepare a fresh decision or publication. |
| `PublicationBlockedError` | Inspect `error.publication.blockers` and the persisted publication snapshot. Resolve the outstanding requirements and prepare again. |

Blocked publication preparations remain available for inspection.

After resolving the blockers, prepare a new publication with the idempotency key omitted or with a new caller-supplied key. Reusing the earlier key returns its recorded blocked outcome.

See [review and publication](review-and-publication.md).

### Retries and concurrent operations

If an application loses its connection after submitting a decision, the operation may already have committed. A missing response does not establish that the operation failed.

The host should recover the outcome using the original operation identity before attempting new work.

| Error | Recommended action |
|---|---|
| `IdempotencyConflictError` | Reuse an existing key only for the same operation and canonical request. Use a new key for new work. |
| `OperationInProgressError` | Retrieve or wait for the existing operation according to its recovery contract. |

Cancellation and lost commit acknowledgements do not establish that a transaction was rolled back.

See [persistence and reliability](persistence-and-reliability.md) for scoped idempotency, transactions, leases, fencing and recovery.

### Artifacts and interoperability

Published model versions and exported artifact identities are immutable. Different content requires a new version or destination.

| Error | Recommended action |
|---|---|
| `ProjectionBlockedError` | Inspect `error.assessment` for capability availability, findings, issues and suggested remedies. Resolve the cause before exporting again. |
| `VersionExistsError` | Retrieve the existing version or select a new version identifier for different content. |
| `ArtifactConflictError` | Reuse the destination only when content and required metadata match. Otherwise, select a different destination. |
| `InvalidBundleError` | Reject the invalid artifact and obtain a valid bundle. |
| `UnsupportedBundleVersionError` | Use a consumer supporting the registered bundle wire version. |
| `InvalidReferencePackError` | Correct the pack and inspect its validation diagnostics. |
| `UnsupportedReferencePackVersionError` | Use a codec supporting the registered reference-pack format. |

Reference-pack composition failures are reported through structured `Issue` diagnostics.

See [bundles and interoperability](bundles-and-interoperability.md) and [reference knowledge and domain types](reference-knowledge-and-domain-types.md).

<a id="detailed-contracts"></a>

## 3. Contract and Usage References

Use the generated API reference for implemented signatures and types. It can be generated through the [local documentation build](../documentation.md#set-up-and-run).

The architecture contracts explain the design and behavioural requirements behind those interfaces.

| Area | References |
|---|---|
| Configuration, clients and projects | [Workspace and configuration](workspace-and-configuration.md), [configuration recipes](../../examples/config/README.md) |
| Source acquisition and evidence | [Sources and evidence](sources-and-evidence.md), [host-parsed evidence](sources-and-evidence.md#already-parsed-evidence) |
| Discovery and reconciliation | [Discovery architecture](discovery-and-reconciliation.md), [live discovery notebook recipe](../../examples/notebooks/README.md#live-discovery) |
| Manual authoring and corrections | [Authoring and domain types](reference-knowledge-and-domain-types.md) |
| Review, validation and publication | [Review and publication](review-and-publication.md) |
| Reference packs and dependencies | [Reference knowledge](reference-knowledge-and-domain-types.md), [reference-pack and dependency recipes](../../examples/notebooks/README.md#reference-packs-and-dependencies) |
| Model changes and dependency upgrades | [Model evolution](model-evolution.md) |
| Bundle consumption and projections | [Bundles and interoperability](bundles-and-interoperability.md) |
| Persistence and recovery | [Persistence and reliability](persistence-and-reliability.md) |
| Notebook and backend applications | [Host integration](host-integration.md), [developer tour](../../examples/notebooks/README.md) |

When changing a capability, update its owning contract and the associated implementation tests. The [contract index](README.md) identifies the authoritative specification for each responsibility.

## 4. Optional Interoperability Roadmap

Domain Kernel can support additional interoperability standards through its existing typed model and adapter contracts.

New integrations should address demonstrated application requirements rather than introduce alternative representations of business knowledge into the core SDK.

The following are potential extensions, not implemented capabilities or release commitments.

| Integration | Potential capability | Development priority |
|---|---|---|
| [QUDT](https://qudt.org/doc/DOC_SCHEMA-QUDT.html) / [UCUM](https://ucum.org/ucum) | Standard quantity and unit terminology, dimensional validation and optional host-controlled conversion. | After typed quantities, particularly for manufacturing. |
| [SSSOM](https://mapping-commons.github.io/sssom/1.0/spec-model/) | Exchange semantic mappings with predicates, provenance, versions and justification. | Early optional interoperability. |
| [R2RML](https://www.w3.org/TR/r2rml/) / [CSVW](https://www.w3.org/TR/tabular-metadata/) | Map relational and tabular operational data to published ontology terms. | Driven by data-integration requirements. |
| [ISA-95](https://opcfoundation.org/markets-collaboration/isa-95/) / [Asset Administration Shell](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1.2/spec-metamodel/overview.html) | Industrial reference packs and specialized interoperability adapters. | Driven by industrial use cases. |
| [RDFC-1.0](https://www.w3.org/TR/rdf-canon/) | Canonical RDF dataset comparison. | After RDF interoperability. |
| [DCAT 3](https://www.w3.org/TR/vocab-dcat-3/) | Catalog metadata and discovery for published models and reference packs. | When catalog integration is required. |
| Advanced projections | Ordered RDF collections, explicit null semantics, decimal facets and richer ontology-to-schema mappings. | Driven by consumer requirements. |
| Extended LinkML, BPMN and DMN | Broader schema, process and decision interoperability. | After the initial bounded mappings. |
| Advanced acceptance checks | Sandboxed model queries and formal entailment-based predicates. | After built-in acceptance checks. |

### Architectural boundaries

Future integrations must preserve the existing separation between business knowledge, semantic representations and operational execution.

- **Units and quantities:** Preserve original unit identities and exact vocabulary versions. QUDT and UCUM do not introduce a general-purpose conversion engine into the core SDK.
- **Semantic mappings:** SSSOM imports enter the review lifecycle. They do not automatically establish OWL identity. Unsupported metadata and information loss must be reported.
- **Operational data:** R2RML and CSVW mappings remain separate from source evidence alignments. Applications own instance extraction and graph population.
- **Industrial knowledge:** Reference packs must not impose a universal manufacturing ontology.
- **Canonicalization:** RDF dataset equivalence is distinct from byte identity and logical equivalence.
- **Catalogs:** DCAT interoperability does not require an SDK-hosted catalog service.
- **Projections:** New mappings require demonstrated semantic fidelity and explicit mapping versions. Static annotated open LinkML value sets already belong to the initial mapping.
- **Processes and decisions:** BPMN and DMN interoperability does not introduce workflow or decision execution.
- **Acceptance checks:** Additional predicates must retain explicit `UNKNOWN` and `UNSUPPORTED` outcomes.

All future adapters must use typed SDK contracts, pinned resources, declared capabilities and the existing review and projection mechanisms.

Selecting an external ontology term does not automatically retrieve resources or install an integration.

RDF 1.1 remains the initial semantic baseline. Newer RDF capabilities require explicitly versioned mappings.

References to external standards describe potential integration opportunities. They do not establish current SDK support or formal standards conformance.

## 5. Verify Cross-Cutting Guarantees

Architecture tests should establish the properties that applications rely on, rather than merely demonstrate that an operation completes successfully.

Use the [testing verification map](../../.agents/skills/domain-kernel-testing/references/verification-map.md) to identify the implementation tests responsible for each guarantee.

### Independent bundle consumption

Maintain a core-only, headless end-to-end test alongside the interactive notebook.

The test must demonstrate that an independent consumer can load and inspect a published bundle without access to the producer's database, inference gateway or optional semantic processing infrastructure.

Verify that the published definitions, approval records and exact dependency identities remain accessible.

The SDK must not require a downstream user interface, production rule engine or graph database to demonstrate its core architectural guarantees.

### Formal semantic contracts

Parsing an RDF document successfully does not establish that a system can reason over its OWL semantics.

Verification must distinguish syntax processing, ontology closure resolution and formal reasoning.

| Area | Required verification |
|---|---|
| Ontology versions | Detect conflicting version pins and ambiguous resource resolution. |
| Import closure | Resolve exact supplied resources, including legal OWL import cycles. |
| Blank nodes | Preserve their applicable document and dataset scope. |
| Multiple inheritance | Preserve formal relationships and combined semantics. |
| OWL punning | Distinguish entity roles that share the same IRI. |
| Open-world cardinality | Distinguish logical restrictions from requirements for explicitly stored values. |
| Logical consistency | Distinguish an unsatisfiable class from an inconsistent ontology. |
| Slices and formal modules | Verify their distinct selection and semantic-preservation contracts. |

A model slice does not provide the entailment-preservation guarantees of a formal ontology module.

Formal guarantees must be verified under the declared reasoning or extraction contract.

### Model evolution and dependencies

Dependency-upgrade tests must establish that changes preserve local identities, historical versions and the applicable consistency boundaries.

Verify:

- Preservation of local definition identities.
- Detection of incompatible dependency pins reached through multiple paths.
- Atomic application of dependency upgrades and necessary local repairs.
- Rejection of stale review decisions.
- Cancellation of generated review members.
- Independent verification of historical releases without the current workspace.

See [model evolution](model-evolution.md).

### Projection fidelity

A generated schema or ontology may be syntactically valid while losing important business requirements.

Projection tests must verify that assessment and actual export agree about which constructs are supported.

Test both supported and rejected data shapes, business keys, vocabularies and constraints. Verify that consumer obligations remain attached to the generated artifacts.

For example, if a mapping cannot distinguish a missing collection from a present empty collection, assessment and export must both reject a model that requires this distinction.

See [bundles and interoperability](bundles-and-interoperability.md).

### Evidence of implementation

Documentation, diagrams and examples explain intended behaviour. They do not establish runtime correctness.

Verify architectural claims through the owning implementation, its applicable tests and recorded conformance evidence.

Keep deterministic workflow verification separate from live discovery evaluation. A replayed inference response can establish that the workflow handles a particular result correctly, but it cannot establish that an inference provider consistently discovers the correct business meanings.
