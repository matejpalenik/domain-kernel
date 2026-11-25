# Purpose and Scope

[Architecture overview](../../ARCHITECTURE.md) · [Contract index](README.md)

<a id="1-the-problem-domain-kernel-solves"></a>

## The Problem Domain Kernel Solves

Business knowledge is rarely documented in one place. It exists across spreadsheets, policies, technical documentation and the experience of the people who work with it.

Consider a manufacturer whose purchasing spreadsheet uses the term `Part` to describe a catalog item. Its purchasing policy calls the same thing a `Component`, while its warehouse documentation uses `Part` to describe an individual serialized physical unit.

A software engineer building an inventory application needs to understand these distinctions before designing its data model. Treating all three terms as equivalent could result in catalog entries and physical inventory being represented as the same business object.

Domain Kernel provides a way to establish these meanings, examine the evidence behind them and preserve the resulting definitions in a reviewed domain model.

| Business question | How Domain Kernel addresses it |
|---|---|
| What does `Component` mean? | Records an explicit definition with a stable identity, meaning, ownership and revision history. |
| Where did that understanding come from? | Links the definition to specific source revisions and supporting passages. |
| Does `Part` mean the same thing? | Records a reviewed alignment or establishes a separate definition. |
| How does a supplier relate to a component? | Defines a relationship with typed endpoints and explicit cardinality. |
| Which questions remain unanswered? | Preserves unresolved review cases, publication blockers and reviewed nonblocking questions. |
| How has our understanding changed? | Compares published versions and reviewed model snapshots. |

Once reviewed and published, this knowledge can be shared across applications without requiring each application to reconstruct the same understanding from the original documents.

## Domain Definitions vs. Operational Data

Domain Kernel distinguishes between defining a business concept and managing the individual records that belong to it.

Consider a component catalog:

| Domain knowledge | Operational data |
|---|---|
| What a component represents | Component `C-123` |
| Which attributes describe a component | Its recorded dimensions and weight |
| How components relate to suppliers | The supplier currently providing `C-123` |
| How inventory quantities are defined | The current stock balance |
| Which purchasing rules apply | Individual purchase orders and transactions |

Domain Kernel manages the left-hand side of this distinction. The consuming application manages the right-hand side.

Operational data may provide useful evidence when developing a domain model. However, observing a field in a spreadsheet does not establish that the field is mandatory, and observing a relationship between two records does not establish that the same relationship applies to every record of those types.

These interpretations require explicit review.

## What Domain Kernel Produces

The primary output is a portable, versioned domain model containing reviewed business concepts, attributes, relationships, constraints, descriptive processes and decisions, together with their provenance.

Different applications can use this knowledge for different purposes:

- A **Business Analysis Platform** can use it to document business requirements and compare current and proposed operating models.
- An **ERP system** can use it to inform data structures, configuration and business rules.
- A **Graph RAG application** can use it to establish the concepts and relationships that guide knowledge extraction.

Domain Kernel provides the model rather than the application implementation. It does not manage inventory, execute business processes, populate instance graphs or deduplicate operational records.

Whether a model is authored manually, developed from reference knowledge or discovered from business evidence, it follows the same review, validation and publication lifecycle.

For information about how the SDK manages that lifecycle, see [architecture and ownership](components-and-ownership.md). For information about using published models in other applications, see [bundles and interoperability](bundles-and-interoperability.md).
