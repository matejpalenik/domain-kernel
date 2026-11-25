# Architecture contracts

[Architecture overview](../../ARCHITECTURE.md)

Start with the chapter that owns the behavior you need to change. The overview
explains how the system fits together; these chapters own the detailed
requirements. [Usage guides](../documentation.md#content-ownership) teach
tasks. The [docs build](../documentation.md#set-up-and-run) generates the API
reference from the public code in this revision.

The SDK is Alpha. A design contract is not evidence that every adapter or
input has been verified. Consult the [capability ledger](../../examples/notebooks/coverage.json)
and owning tests. Discovery is implemented and experimental: it may return
incomplete or incorrect drafts.
[Future extensions](guarantees-and-verification.md#optional-interoperability-roadmap)
are not available APIs.

- [The Problem Domain Kernel Solves](scope.md)
- [Architecture and Ownership](components-and-ownership.md)
- [Configure and Create a Model Workspace](workspace-and-configuration.md)
- [Supply Business Knowledge](sources-and-evidence.md)
- [Discover and Reconcile Meanings](discovery-and-reconciliation.md)
- [Use Reference Knowledge and Richer Definitions](reference-knowledge-and-domain-types.md)
- [Review, Validate, and Publish](review-and-publication.md)
- [Consume the Published Model](bundles-and-interoperability.md)
- [Evolve Models Safely](model-evolution.md)
- [Use Notebooks and Backend Applications](host-integration.md)
- [Storage, Reliability, and Extension Points](persistence-and-reliability.md)
- [Guarantees, Limits, and Reference Map](guarantees-and-verification.md)
