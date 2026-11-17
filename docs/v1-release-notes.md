# Domain Kernel 1.0.0

Domain Kernel is an embeddable, typed Python SDK for preparing reviewed domain models
and transferring exact publications between independent applications. The 1.0.0
candidate includes the SDK wheel, source distribution and version-matched developer tour.

- Review concepts, relationships, business shapes, keys, units and descriptive processes.
  Preserve source citations, local identities and previous publications across explicit
  corrections, reference-pack changes and dependency upgrades.
- Run manually or through a host-owned model gateway. The optional LiteLLM adapter supports
  compatible endpoints that accept the SDK's structured-output schema. Source parsing and
  reconciliation propose candidates for review.
- Use SQLite or the optional PostgreSQL store. Filesystem inputs and outputs, S3 and
  SharePoint have explicit bindings. S3 and SharePoint provider conformance uses mocked
  responses at the adapter boundaries. Credentialed results belong to final acceptance.
- Consume the complete JSON bundle with the core SDK. Optional projections provide RDF,
  SHACL, JSON Schema and LinkML subject to their capability reports and host obligations.
  The formal engine examples exercise the pinned ROBOT 1.9.11 profile and STAR extraction.
- Run the packaged recruitment and manufacturing journeys. The latter verifies parsed
  publisher PDFs, model correction and independent FDE, ERP and GraphRAG consumption.

The package supports Python 3.13 and 3.14. The [compatibility contract](v1-release-acceptance.md)
records wire and mapping versions. The [portable tour setup](../examples/notebooks/README.md#run-the-packaged-tour)
and [release guide](releasing.md) explain installation and integrity verification.
