# V1 conformance evidence

The tests in this report exercise the public SDK or the owning contract. The notebook exercises
business recovery with a reopened workspace, an exact publication retry and a separate consumer.
Fault injection takes place in the test suites.

## Earlier roadmap criteria

| Issue | Automated evidence |
| --- | --- |
| DK-003 · Persistence | [Schema setup](../tests/integration/test_sqlite_schema.py) covers lazy and concurrent setup, independent processes, rollback, explicit setup and cancellation. [Audit](../tests/integration/test_sqlite_audit.py), [leases and cancellation](../tests/integration/test_sqlite_idempotency.py), [database parity](../tests/integration/test_postgresql.py), [publication](../tests/integration/test_publication.py) and [artifact delivery](../tests/integration/test_artifact_delivery.py) cover rollback, recorded diagnostics, exact history, fencing and independently scoped sessions. Source capture, reconciliation, statements, review and compilation have separate owning integration suites. E9 reads the committed event for the exact version and verifies that retry creates no second event. |
| DK-004 · Workspace setup | [Configuration](../tests/unit/test_workspace_configuration.py) and [workspaces](../tests/integration/test_workspaces.py) cover lazy setup, configuration origins, credential separation, named workspace scope and duplicate names. [Discovery](../tests/integration/test_proposal_extraction.py) interprets the same captured statement in two models through independent clients and approves a proposal in one model. The other model retains its own pending case. |
| DK-005 · Leaf review | [Pure review policy](../tests/unit/review/test_leaf_review.py) checks inspected versions, immutable transitions and explicit decisions. [Manual review](../tests/integration/test_manual_review.py) exercises durable proposal/decision history, audit rollback, guarded replay, reservation and typed relationship lookup. |
| DK-006 · Coordinated plans | [Builder and child edits](../tests/unit/modeling/test_model_builder.py), [pure grouped policy](../tests/unit/review/test_leaf_review.py), [grouped persistence](../tests/integration/test_coordinated_review.py) and [pack-change exclusion](../tests/integration/test_reference_catalog.py) check the exact plan, member reservation, contradictory effects, atomic commit, release of pre-existing members and competing decisions. [Graph and revision tests](../tests/integration/test_definition_lifecycle.py) include proposed unit references and reviewed repair of active dependents. |
| DK-007 · Definition identity and history | [Builder](../tests/unit/modeling/test_model_builder.py), [graph rules](../tests/unit/modeling/test_shape_graph.py) and [lifecycle](../tests/integration/test_definition_lifecycle.py) exercise coalesced child edits, retained names and IDs, tombstones, exact inspected revisions, dependent reference repair, typed restoration and paginated history. E9 reloads the recorded restoration from the reopened model. |
| DK-008 · Compilation and readiness | [Compilation](../tests/integration/test_compilation.py), [pure readiness](../tests/unit/modeling/test_readiness.py) and [publication](../tests/integration/test_publication.py) check deterministic content, malformed shapes, independent evidence and confirmation gaps, blocked preparation and changed policy. An advisory question cannot waive a required result. |
| DK-011 · Manual publication | The [quickstart](../examples/recruitment_quickstart.py) and [manual journey](../tests/integration/test_manual_journey.py) prove the first and second releases and independent reload. The [fresh-kernel test](../tests/integration/test_notebook_preview.py) repeats the tour in the same workspace. Both criteria that require a timed newcomer walkthrough remain pending final acceptance. |
| DK-012 · Descriptive process and decision shapes | [Process types](../tests/unit/modeling/test_process_shapes.py), [reviewed process round trip](../tests/integration/test_descriptive_processes.py), [baseline remapping](../tests/integration/test_baseline_copy.py), [slice closure](../tests/integration/test_workflow_slices.py) and [projection limits](../tests/integration/test_json_schema_projection.py) cover typed endpoints, labels, scalar literals, runtime-context omission and exact child identities. |
| DK-030 · Interrupted discovery | [Discovery recovery](../tests/integration/test_proposal_extraction.py) kills a separate process during inference, after saving the draft and after saving its alignment. It resumes the stored run and prompt without repeating completed inference or duplicating the review queue. An expired worker returning late cannot advance the run after another worker takes over. Cancellation and multi-source partial retry are separate scenarios. |

## Adapter and resource checks

- [Source ingestion](../tests/integration/test_source_ingestion.py) checks filesystem
  containment, source revision pins, selection limits, bounded shared concurrency and a slow
  parser. File acquisition and retention renew leases in short transactions while work is in
  progress. An exact retry reopens the same source.
- [Artifact delivery](../tests/integration/test_artifact_delivery.py) checks durable intent,
  expected byte identity, external failure, a slow upload and cancellation after a write.
  A resumed request verifies the original artifact before acknowledging it. Publication history
  stays intact.
- [Tabular](../tests/integration/test_tabular_sources.py), [document](../tests/integration/test_docling_sources.py),
  [S3 and SharePoint](../tests/integration/test_remote_adapters.py) and
  [ontology](../tests/integration/test_ontology_loading.py) suites cover untrusted containers,
  scoped traversal, size limits, exact revisions and explicit import closure. The remote suites
  exercise the shipped adapters against mocked provider boundaries. Credentialed verification
  belongs to final acceptance.
- [Domain import boundaries](../tests/unit/shared/test_import_boundaries.py) check static imports
  inside type-checking blocks as well as imports executed by the interpreter.
  [Gateway tests](../tests/unit/test_litellm_gateway.py),
  [configuration tests](../tests/unit/test_workspace_configuration.py) and
  [renderer tests](../tests/unit/modeling/test_notebook_renderer.py) cover validation, redaction
  and escaped output. Replay and provider conformance are independent of semantic-quality sign-off.
- [Reasoning](../tests/integration/test_ontology_reasoning.py) and
  [module extraction](../tests/integration/test_ontology_modules.py) exercise the exact pinned
  ROBOT 1.9.11 example engine. They verify its named-class reasoning and STAR extraction
  capabilities within the declared profile, including explicit unsupported outcomes.
  [Projection](../tests/integration/test_linkml_projection.py) and
  [SHACL](../tests/integration/test_candidate_shacl.py) tests cover separate interoperability contracts.

## Reproduce the representative workload

Use the pinned inputs, local engine and disposable PostgreSQL schema from the
[tour setup](../examples/notebooks/README.md). Run the full tour twice in fresh kernels with
a shared demo workspace, then compare its release pins and the exact publication audit.
For the controlled Docling run, set the BLAS and OpenMP thread limits to one and use
the verified local weights with Hugging Face offline mode.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
time uv run --locked --no-sync python -m examples.notebooks._preview.validation --verify-resume
```

The workload includes source acquisition and parsing, explicit review, durable replay,
ontology reasoning and extraction, delivery through mocked cloud boundaries and independent
reload on SQLite and PostgreSQL. The test bounds each cell to 90 seconds, with 180 seconds
for the provisioned C3 cell that opens three PDFs and loads OCR weights in a fresh kernel.
The configured per-adapter limits apply. Performance observations describe this workload
and its test machine.

On 17 November 2026, the two-kernel run completed in 162.14 seconds on macOS arm64
with Python 3.13.12 and PostgreSQL 18.6. The macOS time utility reported a maximum
resident set of 2,895,675,392 bytes for the timed workload. Both runs matched the
ledger, including the single publication event, the unchanged prior release and the
exact returned bundle. The separately executed database suite covers contention
and failure cases under both backends.
