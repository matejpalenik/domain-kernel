# Sources and Evidence

[Architecture overview](../../ARCHITECTURE.md) · [Contract index](README.md)

<a id="4-supply-business-knowledge"></a>

Business knowledge can come from documents, spreadsheets, existing ontologies or conversations with the people who understand how an organization operates.

Domain Kernel provides a consistent way to capture these inputs and preserve their provenance. Authors can then use them as evidence when developing or reviewing domain definitions.

Capturing evidence does not establish that its contents are correct. A spreadsheet may contain outdated information, and two people may describe the same business concept differently. These interpretations belong to the modeling and review lifecycle.

## 1. Source Identity and Provenance

A source represents a logical resource within a project, such as a component catalog or purchasing policy.

Its contents may change over time. Domain Kernel preserves those changes as separate revisions so that previously reviewed definitions remain attributable to the evidence originally used.

| Element | Purpose |
|---|---|
| `SourceId` | Permanent identity of the source within the project. |
| Source `name` | Stable, project-local lookup name. |
| `display_name` | Human-readable label that can change independently of identity. |
| Revision digest | Identifies the exact original file bytes or canonical captured payload. |
| Provider version or ETag | Records upstream resource metadata without replacing the content digest. |
| Processing fingerprint | Identifies the parsing and extraction configuration used. |
| Evidence citation | Identifies a location within a particular source revision. |

File revisions use a SHA-256 hash of the complete original file, even when only selected pages or worksheets are processed.

Processing fingerprints remain separate from source identity. Parsing the same document using a different configuration does not create a new source revision.

### Source names and revisions

Sources follow the shared [naming conventions](workspace-and-configuration.md#project-and-model-names).

The SDK generates a permanent `SourceId` and a stable lookup name from the supplied display name, unless an explicit name is provided. Supplying `name` alone is also supported.

Source names are unique within the project's source catalog, independently of model names. Display names may repeat.

Names identify catalog entries rather than filesystem locations. Moving a file or changing its display name does not regenerate its stable name or ID.

| Operation | Behaviour |
|---|---|
| `ingest_source()` | Create a logical source and its first revision. |
| `ingest_source_revision()` | Capture new content under an existing source identity. |
| `get_source()` | Retrieve an existing source using its exact name or ID. |

`get_source()` requires exactly one of `name` or `source_id`.

Missing sources raise `SourceNotFoundError`. Foreign source IDs raise `ScopeMismatchError`.

Creating a source with an existing name raises `SourceAlreadyExistsError`, including during concurrent creation. The SDK does not append suffixes or implicitly update an existing source.

Revision hashes exclude catalog naming metadata. Identical file bytes or canonical captured payloads under the same source reuse the same revision.

Existing revision provenance is immutable. Reacquiring the same resource cannot overwrite its original capture information.

## 2. Files and Citations

Domain Kernel supports documents, structured files and ontology resources through configured source readers and parsers.

The `path` argument is shorthand for a location within the configured `inputs` reader, whether that reader accesses a local filesystem or remote storage.

Use `ReaderLocation` when selecting a particular reader explicitly.

### Ingest a file

```python id="4n8mxk"
from domain_kernel import PDF, Excel, ReaderLocation

components = await project.ingest_source(
    actor="user:model-editor",
    source=Excel(path="components.xlsx"),
    display_name="Components",
)

policy = await project.ingest_source(
    actor="user:model-editor",
    source=PDF(
        location=ReaderLocation(
            reader="inputs",
            path="catalog-policy.pdf",
        ),
    ),
    display_name="Catalog policy",
)
```

Each operation creates a source and captures its first revision.

Install `domain-kernel[documents]` and configure `[parsers.documents]` with `type = "docling"` to process supported document and tabular formats, including PDF, Word, CSV and Excel.

When a parser is unavailable and the descriptor selects the complete file, ingestion can still capture the original revision without parsing its contents.

The source profile records which selected units were processed and which could not be read.

### Profile structured data

Source profiling helps authors understand the structure of an ingested file before developing domain definitions.

For example, a component spreadsheet may contain columns for component numbers, descriptions and supplier codes. Profiling can identify their observed types, nullability and possible identifier columns.

```python id="ug8kn2"
profile = await project.profile_source(
    actor="user:model-editor",
    revision=components.revision,
)

for table in profile.tables:
    print(f"{table.name}: {table.row_count} rows")

    for column in table.columns:
        print(
            column.name,
            column.inferred_type.value,
            column.nullable,
            column.identifier_candidate,
        )

for issue in profile.issues:
    print(f"{issue.code}: {issue.message}")
```

Profiling describes the source data. It does not use inference to establish business meanings or create domain definitions.

An apparently unique spreadsheet column is an identifier candidate, not an approved business key. Likewise, a column containing no missing values does not establish that the corresponding business attribute must always be present.

These requirements need explicit authoring and review.

### Tabular profiling contracts

Tabular profiles preserve ordered column metadata and candidate identifiers.

Sample citations cover the first sixteen non-empty data rows of each Excel worksheet or the first sixteen CSV data records.

CSV coordinates count logical records rather than physical lines, including records containing quoted multiline cells. Excel coordinates retain the original worksheet row numbers.

`InMemoryProcessing` bounds the number of tables and their rectangular cell extents.

The persisted profile contains metadata and citations. The verified source file remains authoritative for row values.

Recovering a sample requires reopening the exact file revision using its recorded parser version and options.

### Document parsing

Register `DoclingParser()` for the `"pdf"` and `"word"` formats when using the documents extra.

| Configuration | Capability |
|---|---|
| Native PDF pipeline | Extract embedded text without model weights. |
| `DoclingParser(artifacts_path=local_models, ocr=True)` | Enable layout, table and English OCR processing using explicitly configured local model artifacts. |

Normalized PDF evidence spans use offsets within the extracted text of a page.

Word evidence spans use offsets in document order and may identify a heading or table.

Enable `Retention(extracted_text=True)` to preserve normalized document content for subsequent evidence inspection.

SQLite schema version 10 introduces the retained-document table. Upgrading earlier supported schemas remains an explicit deployment operation.

See [persistence and reliability](persistence-and-reliability.md) for storage, retention and resource limits.

## 3. Batch Ingestion and Folder Selection

Applications can ingest several independently named sources or select files from configured folders in one operation.

`ingest_sources()` accepts `SourceInput` and `SourceFolder` entries.

- `SourceInput` groups a source descriptor with its naming, retention and retry arguments.
- `SourceFolder` expands a folder or storage prefix into individual sources.

Bare file descriptors are not valid batch entries. The batch actor applies to every item.

A folder is a selection mechanism rather than a combined document. Every selected file retains its own source identity and revision.

### Ingest files and folders

The following example assumes configured `local`, `sharepoint` and `s3` readers and the required parser integrations.

```python id="d3m8vr"
from domain_kernel import (
    CSV,
    PDF,
    Ontology,
    ReaderLocation,
    SourceFolder,
    SourceInput,
    Word,
)

batch = await project.ingest_sources(
    actor="user:model-editor",
    sources=[
        SourceInput(
            display_name="Suppliers",
            source=CSV(
                location=ReaderLocation(
                    reader="local",
                    path="suppliers.csv",
                ),
            ),
        ),
        SourceInput(
            display_name="Catalog rules",
            source=Word(
                location=ReaderLocation(
                    reader="local",
                    path="catalog-rules.docx",
                ),
            ),
        ),
        SourceInput(
            display_name="Company terms",
            source=Ontology(
                location=ReaderLocation(
                    reader="local",
                    path="company-terms.ttl",
                ),
                format="turtle",
            ),
        ),
        SourceInput(
            display_name="Installation guide",
            source=PDF(
                location=ReaderLocation(
                    reader="local",
                    path="installation.pdf",
                ),
            ),
        ),
        SourceFolder(
            location=ReaderLocation(
                reader="sharepoint",
                path="Engineering",
            ),
            recursive=True,
            name_prefix="engineering",
        ),
        SourceFolder(
            location=ReaderLocation(
                reader="local",
                path="policies",
            ),
            recursive=False,
            name_prefix="policies",
        ),
        SourceFolder(
            location=ReaderLocation(
                reader="s3",
                path="specifications",
            ),
            recursive=True,
            include=["**/*.pdf", "**/*.docx"],
            exclude=["**/archive/**", "**/~$*"],
            name_prefix="specifications",
        ),
    ],
)

print(f"Ingested: {len(batch.successes)}")
print(f"Failed: {len(batch.failures)}")
```

The operation inherits the configured source-processing and file-selection limits.

Successful revisions remain available even when other independently selected sources fail.

### Folder traversal and filtering

Folder selection follows the same contract across filesystems, SharePoint folders and S3 prefixes.

| Setting | Behaviour |
|---|---|
| `recursive=False` | Select direct files only. |
| `recursive=True` | Include files in descendant folders. |
| `path="."` | Select the configured reader root. |
| `include` | Select matching relative paths. An empty selection includes all files. |
| `exclude` | Remove matching paths from the selection. Exclusion takes precedence. |

Locations are relative to their configured reader.

S3 folder selections use slash-delimited prefixes. Selecting `specifications/` must not include objects under `specifications-old/`.

Filesystem symlinks and SharePoint shortcuts must not be followed. Unsupported links are reported explicitly.

Include and exclude patterns match case-sensitive, slash-separated paths relative to the selected folder.

`*` and `?` match within a path segment. A complete `**` segment matches zero or more directory levels, including direct files.

Absolute paths and traversal patterns are rejected. Filtering cannot override `recursive=False`.

### File format selection

Folder expansion selects descriptors according to recognized file extensions.

| Extension | Descriptor or syntax |
|---|---|
| `.pdf` | `PDF` |
| `.docx` | `Word` |
| `.xlsx` | `Excel` |
| `.csv` | `CSV` |
| `.ttl` | Turtle ontology |
| `.rdf` | RDF/XML ontology |
| `.jsonld` | JSON-LD ontology |
| `.nt` | N-Triples ontology |

Extension dispatch is case-insensitive. Include and exclude patterns remain case-sensitive.

Parsers must validate the actual file content. Unsupported or ambiguous formats and missing adapters produce individual file issues.

Use explicit `SourceInput` entries for files requiring custom names, selected PDF pages, selected Excel worksheets or other descriptor-specific options. Exclude those files from automatic folder selection where necessary.

### Generate source names

Folder expansion derives `display_name` from the filename without its final extension.

The stable source name is generated from the validated optional `name_prefix` and relative path, excluding the final extension.

For example:

| Property | Value |
|---|---|
| Selected folder prefix | `engineering` |
| Relative file path | `Pumps/Maintenance.pdf` |
| Display name | `Maintenance` |
| Stable source name | `engineering-pumps-maintenance` |

IDs remain independently generated by the SDK.

Invalid names and collisions fail rather than receiving suffixes.

Equivalent overlapping selections referring to the same reader and provider identity are coalesced, linking their retry keys to one outcome.

Conflicting naming choices, descriptor options or provider pins fail explicitly.

Moving a file does not rename a previously created source.

### Selection and concurrency limits

Source selection and content acquisition are bounded independently.

| `SourceSelectionLimits` setting | Default |
|---|---:|
| Selected files | 1,000 |
| Listing entries | 10,000 |
| Descendant folder depth | 32 levels |
| Enumeration time | 60 seconds |

The operation inherits `processing.max_concurrent_sources` and `source_selection.max_files`.

Positive per-call overrides may lower these ceilings but cannot exceed the configured limits.

A fixed worker pool shares the client's processing capacity across simultaneous batch and individual ingestion operations.

Listing budgets apply across the entire call, including entries removed by filters. The selected-file limit counts files after deduplication, including files whose formats are unsupported.

The SDK expands and checks selections before reading their contents.

Exceeding a limit fails explicitly rather than accepting a silently truncated selection.

Empty folders are valid and produce no document outcomes.

Provider I/O remains outside database transactions.

## 4. Batch Outcomes, Retries and Recovery

A batch may contain valid documents alongside inaccessible files, unsupported formats or conflicting source names.

Applications should inspect those outcomes before deciding whether the successfully captured revisions provide enough evidence to proceed.

### Inspect batch results

`BatchIngestionResult.items` contains typed `IngestionSuccess` and `IngestionFailure` records.

The `successes`, `failures` and `revisions` properties are immutable derived views. Only successful items appear in `revisions`.

Results retain caller order, followed by relative-path order within each folder, regardless of concurrent completion timing.

```python id="ki82vc"
for failure in batch.failures:
    location = failure.location

    label = f"{location.reader}:{location.path}" if location is not None else "Non-file input"

    print(
        f"{label}: {failure.stage.value} — "
        f"{failure.message} "
        f"[code={failure.code}, retryable={failure.retryable}]"
    )
```

Each failure retains its original input, optional location, structured issue, retryability and processing stage.

| Stage | Meaning |
|---|---|
| `IngestionStage.LISTING` | A folder could not be enumerated completely. |
| `IngestionStage.NAMING` | A selected source could not be assigned a valid, compatible catalog name. |
| `IngestionStage.INGESTION` | Acquisition, parsing or another ingestion operation failed. |

The `message`, `code` and `severity` properties expose the corresponding values from the existing structured `issue`. Severity remains an `IssueSeverity` enum.

The issue retains its diagnostic path without duplicating serialized fields.

### Partial success

A listing failure imports no files from the incompletely enumerated folder. Independent selections may continue.

An individual document failure does not roll back previously successful source ingestion.

Invalid batch arguments fail during preflight. Cancellation and fatal coordination failures propagate while retaining earlier durable commits.

An empty batch is not evidence of successful source acquisition. Inspect its outcomes separately.

### Retry a folder selection

A folder can change between requests. Files may arrive, disappear or receive new versions.

To prevent retries from processing a different selection, folder retry keys identify immutable manifests.

A captured manifest records:

- Resolved entries.
- Naming and descriptor options.
- Provider identities and available version tokens.
- Stable per-file operation keys.

Matching retries reuse the recorded selection. Newly arrived files require a new scan.

A failed listing may be retried until its first complete capture.

Manifest metadata, attribution and the replay outcome commit together before child ingestion begins. Individual source commits remain independent and attributed.

Generated child keys preserve their manifest guards, including when retrying only a subset of the selected files.

Explicit `SourceInput` keys retain the ordinary single-source replay contract.

Omitting a key creates fresh invocation intent without a cross-call replay guarantee.

A folder listing is not an atomic snapshot of a live storage system. The SDK hashes file bytes during acquisition and must honor available provider pins or fail.

A new scan does not silently update or remove existing sources. Changed content requires `ingest_source_revision()`.

### Single-source transaction guarantees

Individual ingestion commands require an actor and support scoped idempotency.

A matching retry returns the recorded result before duplicate-name checks or another read of the input. Changed request content under the same key produces a conflict.

New source or revision metadata, audit records and the operation outcome commit together under the applicable unique-name and source-version guards.

Failed ingestion must not leave a partially accepted source or revision.

Provider I/O and explicit original retention follow the external-write recovery contract.

See [persistence and reliability](persistence-and-reliability.md) for transaction boundaries and idempotency.

### Continue to discovery

The application decides whether to proceed with the successfully captured revisions after inspecting all batch failures.

```python id="hdpx4f"
run = await model.discover(
    actor="user:model-editor",
    sources=batch.revisions,
)
```

This is a separate, explicitly initiated operation.

Ingestion and profiling never start discovery automatically.

See [discovery and reconciliation](discovery-and-reconciliation.md).

## 5. Retrieve Supporting Evidence

An evidence citation identifies where supporting information was found. It does not necessarily contain the original passage.

This separation allows Domain Kernel to preserve provenance without automatically retaining every source document or extracted excerpt.

### Inspect an evidence citation

When an ingestion result contains evidence citations, select the relevant citation and retrieve its contents:

```python id="rz4vnp"
if components.evidence:
    citation = components.evidence[0]

    content = await project.get_evidence(
        evidence=citation,
    )

    print(content.excerpt)
```

`get_evidence()` returns `EvidenceContent`, containing the excerpt, its citation and verified acquisition `origin`.

Citations can identify locations such as:

| Source | Evidence location |
|---|---|
| Spreadsheet | Worksheet cells or ranges. |
| CSV | Logical record coordinates. |
| PDF | Page and extracted-text span. |
| Word document | Document-order span, heading or table. |
| Attributed statement | Statement text span. |
| Ontology | Semantic resource location. |
| Host-parsed source | Stable external locator. |

The citation remains separate from the content returned during evidence retrieval.

### Retention and availability

Original-file retention, normalized-content retention and evidence-excerpt retention are independently configurable.

When retrieving evidence, the SDK may use:

- A retained excerpt.
- Retained normalized content.
- The exact original file recovered through its configured reader.
- A verified archive in a configured readable original store.
- An exact host-parsed capture recovered through its configured resolver.

Whatever recovery path is used, the content must match the recorded source revision and applicable processing contract.

If a supplier replaces a catalog after a model has been published, the updated document cannot substitute for the original evidence.

Missing or changed evidence produces an explicit failure.

Evidence citations remain available in proposals and published bundles, but their presence does not guarantee that the underlying content will remain accessible.

See [retention policies](persistence-and-reliability.md#retention-policies).

## 6. Manual Definitions and Attributed Statements

Not all business knowledge is documented.

A catalog owner may understand why two apparently identical records represent different business concepts. An engineer may clarify how equipment identifiers are assigned.

Authors can introduce such meanings directly through the [typed authoring API](reference-knowledge-and-domain-types.md#author-connected-domain-definitions).

When the source of the interpretation matters, an attributed statement allows the author to preserve what was said, who said it and where the claim applies.

### Capture an attributed statement

```python id="h8j2wc"
from datetime import datetime, timezone

from domain_kernel import (
    Person,
    PersonId,
    Statement,
    StatementForm,
    StatementIntent,
)

owner = Person(
    id=PersonId(value="person:catalog-owner"),
    name="Catalog owner",
    role="Catalog owner",
)

statement = await project.ingest_source(
    actor="user:model-editor",
    display_name="Component identifier meaning",
    source=Statement(
        text=("Component numbers identify catalog entries, not individual physical units."),
        speaker=owner,
        stated_at=datetime(
            year=2026,
            month=11,
            day=1,
            tzinfo=timezone.utc,
        ),
        context="Component identifiers in the company catalog.",
        form=StatementForm.QUOTATION,
        intent=StatementIntent.ASSERTION,
    ),
)
```

The statement becomes a versioned source that can support manually authored definitions or participate in discovery.

### Statement attribution

A captured statement distinguishes the person supplying information from the person recording it.

| Field | Purpose |
|---|---|
| `speaker` | Stable identity, name and role of the person making the statement. |
| `recorded_by` | Identity of the person or system recording it. |
| `stated_at` | Original time of the statement, if known. |
| `recorded_at` | SDK-assigned capture timestamp. |
| `context` | The circumstances or business scope to which the statement applies. |
| `form` | Whether the captured text is a quotation or summary. |
| `intent` | Whether the statement represents an observation, proposal or assertion. |

`context` is required, non-blank text. It does not replace or modify the model description.

Both `form` and `intent` are required. They describe the captured statement without verifying its correctness.

When `recorded_by` is omitted or `None`, the SDK resolves it once from the ingestion actor and persists that concrete identity. This applies to individual ingestion, batch ingestion and revision ingestion.

Supply `recorded_by` explicitly when the recorder differs from the ingestion actor.

### Statement time and revision identity

An omitted or `None` `stated_at` means the original statement time is unknown.

A supplied timestamp must be timezone-aware.

The SDK must not substitute the ingestion time for an unknown statement time. It records `recorded_at` separately as audit metadata.

Statement revision digests identify the canonical captured payload, including the resolved recorder, context and original statement time.

Unknown statement times use canonical null. The SDK-assigned `recorded_at` timestamp remains outside the revision digest.

Matching retries preserve the original attribution and timestamps.

Recording a statement establishes its provenance, not its business correctness.

When an interpretation requires explicit confirmation, follow the separate [confirmation review contract](review-and-publication.md).

<a id="already-parsed-evidence"></a>

## 7. Host-Parsed Evidence

Some applications already have document acquisition and parsing pipelines.

For example, a Business Analysis Platform or Graph RAG application may extract text and tables from documents before invoking Domain Kernel.

Rather than downloading and parsing those documents again, the application can supply its captured content directly through `ParsedSource`.

### Configure a parsed-source provider

Register a named `ParsedSourceProvider` through `ClientIntegrations.parsed_source_providers` when creating the client.

The provider associates a stable name with the application's `ParsedSourceResolver`.

Registering the provider does not retrieve any content.

`ParsedSourceOrigin.provider` identifies the configured provider. Existing project and model handles reuse the integrations belonging to their client.

The resolver must reproduce the exact captured content under the application's access policies.

### Ingest parsed content

The following example assumes that a provider named `content-platform` has already been configured.

```python id="k7t3ha"
from datetime import datetime, timezone

from domain_kernel import (
    ExternalLocation,
    ParsedSource,
    ParsedSourceOrigin,
    ParsedText,
)

capture = await project.ingest_source(
    actor="user:model-editor",
    display_name="Parsed catalog policy",
    source=ParsedSource(
        origin=ParsedSourceOrigin(
            provider="content-platform",
            document_id="catalog-policy",
            document_revision="v7",
            captured_at=datetime.now(tz=timezone.utc),
        ),
        parts=[
            ParsedText(
                text="A supplier provides catalog components.",
                locator=ExternalLocation(
                    key="section:suppliers",
                ),
            ),
        ],
    ),
)
```

The host provides the upstream document identity, revision and stable locators together with the captured content.

Supported parsed inputs include:

| Type | Content |
|---|---|
| `ParsedText` | Text with a stable external locator. |
| `ParsedTable` | Columns, rows and optional row locations. |
| `ParsedGraph` | Captured semantic statements. |

The SDK uses these inputs as evidence through the ordinary source and modeling contracts.

### Provenance and content integrity

Domain Kernel calculates the revision digest from the canonical parsed payload, including upstream document identity, revision, content and locators.

Acquisition timestamps are excluded.

If the host supplies an original-file digest, it remains an attributed host assertion. The SDK does not claim to have verified original bytes it has not acquired.

External locators are identifiers rather than URLs that the SDK automatically accesses.

When evidence is requested, the SDK retrieves retained content or invokes the configured resolver and verifies the recovered capture digest.

If the exact capture cannot be recovered, evidence access fails.

Default retention settings do not guarantee future replay.

### Discover from parsed evidence

Once captured, host-parsed revisions can participate in the ordinary discovery workflow:

```python id="h2nx7j"
run = await model.discover(
    actor="user:model-editor",
    sources=[capture.revision],
)
```

The model's existing client provides the configured resolver and, where inference is required, the model gateway.

The host continues to own its acquisition pipeline, access policies and transport. Domain Kernel owns the captured source identity, evidence references and their use within the domain model lifecycle.

## Further Reading

| Contract | Reference |
|---|---|
| Source naming, configuration and provider registration | [Workspace and configuration](workspace-and-configuration.md) |
| Discovery and evidence-assisted interpretation | [Discovery and reconciliation](discovery-and-reconciliation.md) |
| Manual authoring and ontology resources | [Reference knowledge and domain types](reference-knowledge-and-domain-types.md) |
| Attributed confirmations and review | [Review and publication](review-and-publication.md) |
| Retention, transactions and recovery | [Persistence and reliability](persistence-and-reliability.md) |
| Application integration | [Host integration](host-integration.md) |
