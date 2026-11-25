# Domain Kernel

Domain Kernel deals with reusable business definitions and the evidence for
them. The glossary distinguishes those definitions from facts about particular
records.

## Language

### Model and reference

**Domain Model**:
The reusable representation of a business domain for a stated purpose,
including concepts, relationships, constraints, and relevant processes and
decisions. It describes kinds of things and what can hold for them, not the
business records themselves.
_Avoid_: Taxonomy or ontology as a blanket synonym

**Domain Model Draft**:
A set of proposed definitions or changes to a domain model, with evidence and
any open decisions. A draft is reviewable but is not an approved or published
model.
_Avoid_: Approved model, published model

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
A curated collection of reusable definitions, patterns, and obligations
supplied as a modeling reference. It may include material from a reference ontology.

### Discovery and evaluation

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
