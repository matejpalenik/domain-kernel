# Domain Kernel 0.1.0 acceptance

## Reproduce the release candidate checks

1. Verify the package checksums. Install the SDK wheel matching the
   [portable tour version](../examples/notebooks/README.md#run-from-a-release-archive).
2. Run `pnpm test`, `pnpm test:integration`, `pnpm test:notebook` and `pnpm check` from
   the exact source revision. Use the [release guide](releasing.md#3-build-and-verify-the-distributions)
   to repeat the isolated wheel, source and extras checks on Python 3.13 and 3.14.
3. Run the unpacked tour in two fresh kernels against the same disposable workspace.
   Compare the delivered bundle and publication audit across runs. Provision the pinned originals,
   workbook, ontology closure, OCR weights, ROBOT JAR and disposable PostgreSQL schema for
   the separate specialist checks in the [coverage ledger](../examples/notebooks/coverage.json).
4. Run the [manual manufacturing handoff](../examples/notebooks/README.md#manufacturing-and-independent-hosts)
   against the unpacked tour and installed wheel. Confirm the earlier pressure maximum of
   four and the reviewed maximum of five. The FDE, ERP and GraphRAG hosts load the delivered
   files after the temporary producer workspace is removed.
5. Consult the [conformance report](v1-conformance.md) for actual failure, recovery,
   resource and security fixtures. Code demonstrating the business workflow lives in the
   guide and notebook.

## Gateway evidence

See the [v23 discovery evidence](evidence/discovery-v23.md). The benchmark measures
provisional coverage, not release acceptance. The notebook's automated restart check
uses scripted responses, not live gateway evidence.

## Compatibility contract

| Contract | Frozen version and scope |
| --- | --- |
| Python SDK | Domain Kernel 0.1.0 on Python 3.13 and 3.14. Package-root exports, keyword-only contracts and the `py.typed` marker are checked. |
| Complete bundle | `domain-kernel.bundle` schema 1.0 and semantic mapping 1.0. The bundle preserves supported definitions, revision and review provenance, authorization, exact dependencies and source pins. Artifact byte hashes identify transport bytes separately from semantic model hashes. |
| Reference pack | The standalone version 1.0 codec preserves exact pack dependencies and provenance. Attach, replacement and removal each use reviewed workspace operations. |
| RDF and SHACL | `dk-rdf/1.0`, RDFLib 7.6.0 and pySHACL 0.40.2. Separate ontology, metadata, model shapes and instance shapes retain exact model pins. Ordered lists and structural equality of nested sets require another representation. |
| JSON Schema | `dk-json-schema/1.0` with Draft 2020-12. Supported record shapes preserve declared bounds and vocabulary. Cross-record keys and reference targets are explicit consumer obligations. |
| LinkML | `dk-linkml/1.0` with linkml-runtime 1.12.1. Supported import creates local proposals and retains typed unit and shape metadata. Dynamic vocabularies remain outside the mapping. |
| Ontology engines | ROBOT 1.9.11, HermiT 1.4.5.456 and OWLAPI 4.5.29. The examples test named-class reasoning for the declared OWL 2 DL profile and STAR locality extraction on explicitly supplied closures. |
| Documents and tables | Docling 2.149.0, DuckDB 2.0.0 and Openpyxl 3.1.5. Provenance distinguishes original bytes, parsed streams and bounded derived captures. |
| Gateway and storage | LiteLLM 1.108.4, SQLAlchemy 2.1.8 with the locked SQLite and Psycopg 3.3.8 adapters, PostgreSQL 18.6, Boto3 1.43.127 and HTTPX 0.28.1 with Microsoft Graph v1.0. Live Luna and mocked remote verification have separate evidence. |

Incompatible wire or mapping changes require a registered version and identifiable capability
report. Persistence schema revisions follow the explicit operator setup and upgrade contracts.
The SDK package version, model release version, schema version and mapping version are separate.

## One final human acceptance session

Run this session after the implementation and release-preparation PRs reach `main`. Record each
outcome against the candidate package version, frontend and exact edition or provider binding.

1. Give a developer the README. Use the [newcomer session](../examples/notebooks/VALIDATION.md#newcomer-session)
   to time the journey from a fresh notebook kernel to an independent bundle read. Compare it
   with the ten-minute target after provisioning. Review the correction, its citation and the
   new release, and confirm the earlier release is unchanged.
2. Observe the walkthrough in their notebook frontend and compare the offline reading version.
   Use a disposable handoff case to check keyboard input, light and dark modes, and stale and
   duplicate submissions. Verify that the code-only recovery path works without the review control.
3. Review the [frozen Act expectations](../examples/notebooks/fixtures/discovery-expectations.json)
   and [guidance update rubric](../examples/notebooks/fixtures/discovery-update-expectations.json)
   before opening the private candidate provider receipt. Compare meanings, relationship directions,
   citations, mappings, omissions and review effort. Record the semantic judgment separately from
   the replay and automatically checked lookup/page results.
4. Run the [credentialed S3 and SharePoint recipes](../examples/notebooks/README.md#s3-and-sharepoint)
   once the host bindings can be configured. Compare exact selected items, byte hashes and
   revisions, then verify delivery with the output binding and its own credentials.

Record the human results alongside the [automated conformance evidence](v1-conformance.md).
Tagging and distribution publication follow the [release process](releasing.md).
