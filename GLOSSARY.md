# Domain Kernel

Domain Kernel deals with reusable business definitions and the evidence for
them. The glossary distinguishes those definitions from facts about particular
records.

## Language

### Model and reference

**Project**:
A shared scope for sources and independently maintained model workspaces.
_Avoid_: Tenant, security boundary

**Domain Model**:
The reusable representation of a business domain for a stated purpose,
including concepts, relationships, constraints, and relevant processes and
decisions. It describes kinds of things and what can hold for them, not the
business records themselves.
_Avoid_: Taxonomy or ontology as a blanket synonym

**Model Workspace**:
The editable home of an observed or proposed domain model within a project.
It contains definitions and their review state, and may use an exact version
of a reference pack.
_Avoid_: Published model, bundle

**Domain Model Draft**:
A set of proposed definitions or changes to a domain model, with any supporting
evidence and open decisions. A draft is reviewable but is not an approved or
published model.
_Avoid_: Approved model, published model

**Definition**:
A named business meaning expressed as a concept, relationship, constraint,
or another kind of model content. Its identity can stay the same across
revisions that preserve that meaning.

**Domain Graph**:
The definitions in a model and the connections between them.
_Avoid_: Instance graph

**Instance Data**:
Records and facts about particular business objects or events, such as the
location of one serialized unit. Consuming applications own these records.
_Avoid_: Domain definitions

**Vocabulary**:
The terms and labels used to name meanings in a domain. A vocabulary alone
does not specify how those meanings relate or which rules govern them.

**Controlled Vocabulary**:
A governed set of terms or codes for named meanings, with rules for preferred
labels or accepted variants. It does not require a hierarchy.

**Taxonomy**:
A controlled vocabulary organized into broader and narrower categories for
classification. A broader category does not by itself imply formal subclass
inheritance.
_Avoid_: Ontology, when classification is all that is meant

**Formal Ontology**:
A specification of domain terms and axioms under explicit, machine-interpretable
semantics. A formal ontology can express part of a domain model without being
the whole model.
_Avoid_: Vocabulary or RDF serialization as a synonym

**Reference Ontology**:
A formal ontology consulted for reusable terms or axioms. Aligning a local term
with a reference term is not the same as adopting the reference axioms.

**Reference Pack**:
A versioned collection of reusable definitions, patterns, and obligations
supplied as a modeling reference. It may include material from a reference
ontology.

**Ontology Term Reference**:
A reference to a term in an exact ontology resource that preserves its original
IRI and entity kind.
_Avoid_: Adopted ontology module

**Ontology Closure**:
The exact ontology documents selected for an ontology and all its reachable
imports.

### Descriptive processes

**Descriptive Process**:
A definition of how business work is meant to proceed, including the roles,
activities, events, and paths involved. It does not execute or track that work.
_Avoid_: Executable workflow, process run

**Process Role**:
A responsibility in a descriptive process, not the person assigned to it or an
access-control role.

**Process Activity**:
A named step of work in a descriptive process.

**Process Event**:
A kind of occurrence that marks a point in a descriptive process, such as
receiving a catalog entry. It is not a record of a particular occurrence.

**Process Flow**:
A directed connection between activities, events, or gateways in a descriptive
process.

**Process Gateway**:
A split or join in a descriptive process. An exclusive gateway describes
alternative paths; a parallel gateway describes paths that can proceed together.
_Avoid_: Model gateway, which is used for inference.

**Process Split**:
A process gateway where one incoming path branches into multiple outgoing paths.

**Process Join**:
A process gateway where multiple incoming paths converge into one outgoing path.

**Condition**:
A stated criterion for taking a conditional process flow or matching a business
decision rule. The description does not evaluate the criterion.

### Descriptive business decisions

**Business Decision Table**:
A definition of how stated conditions and inputs relate to intended outcomes.
It describes a business decision, not an execution of one.
_Avoid_: Review Decision, decision engine

**Decision Input**:
A named piece of information a business decision considers. Conditions refer
to inputs by their local keys.

**Decision Output**:
A named result of a business decision with a declared scalar type.

**Decision Rule**:
A row in a business decision table that associates stated conditions with
values for the declared outputs.
_Avoid_: Cardinality constraint, Review Decision

**Hit Policy**:
The stated convention for selecting or collecting results when decision rules
match.

### Discovery and evaluation

**Source Revision**:
A fixed version of the content of a source, independent of how it is read or
parsed.

**Processing Capture**:
A record of how an exact source revision was read or parsed, including which
part was selected.

**Evidence**:
Information from a source or attributed statement that supports or qualifies
a proposed business meaning.
_Avoid_: Proof of correctness

**Evidence Citation**:
A reference to the exact source revision, processing capture, and location
of supporting information. It is not a copy of the cited material.
_Avoid_: Excerpt

**Proposal**:
A suggested business meaning or model change, not an accepted definition.

**Schema Discovery**:
Identifying reusable concepts, relationships, and scoped rules from evidence
and the modeler's stated purpose. The result is a domain model draft, not a
collection of business records.
_Avoid_: Instance population, fact extraction

**Instance Population**:
Creating or updating records about particular entities or events and asserting
facts about them using a model.
_Avoid_: Schema discovery

**Competency Question**:
A question that states what a model should let someone answer for a particular
use. It scopes the model but does not by itself establish facts or rules.

**Competency Requirement**:
A meaning or distinction that a model must preserve to answer a competency
question as intended.
_Avoid_: Lemma, when referring to a model requirement rather than a proved assertion

**Instance Fixture**:
An authored example or counterexample used to check what a schema can represent
or constrain. It is not a record extracted by the workflow under test.
_Avoid_: Extracted record, production data

### Review and publication

**Review Case**:
A proposed change or open question that calls for an explicit decision.

**Review Decision**:
An attributed judgment about a review case that records what was decided and
why.
_Avoid_: Publication approval

**Candidate**:
A fixed snapshot of reviewed model content for validation. A candidate alone
does not establish readiness or authorize release.

**Publication**:
A record of an exact candidate with its validation and readiness results,
dependency pins, and change information. A publication can be ready or blocked;
it is not a release.
_Avoid_: Bundle, published version

**Approval**:
The attributed authorization to release an exact publication as a specific
model version.
_Avoid_: Acceptance of a review case

**Bundle**:
An immutable, portable copy of a published model version, including its
provenance and release authorization.
_Avoid_: Projection, candidate

### Model consumption

**Model Composition**:
A read-only view of exact published models together. Each model keeps its own
version and definitions; matching names do not merge meanings.

**Model Slice**:
A focused view of selected definitions and the supporting content needed to
resolve their references.
_Avoid_: Formal ontology module

**RDF Projection**:
A representation of supported content in a published model as RDF graphs.

**SHACL Shape**:
A declaration of requirements for validating an RDF graph, such as the graph
of model metadata or a graph of downstream business records.

**LinkML Projection**:
A LinkML schema that represents the supported parts of a published domain model.

**Artifact**:
An exported file or retained source file with a recorded identity and associated
metadata.
