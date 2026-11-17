# Domain Kernel 1.0.0 acceptance

## Reproduce the release candidate checks

1. Verify the package checksums. Install the SDK wheel matching the
   [portable tour version](../examples/notebooks/README.md#run-the-packaged-tour).
2. Run `pnpm test`, `pnpm test:integration`, `pnpm test:notebook` and `pnpm check` from
   the exact source revision. Use the [release guide](releasing.md#3-build-and-verify-the-distributions)
   to repeat the isolated wheel, source and extras checks on Python 3.13 and 3.14.
3. Provision the pinned originals, workbook, ontology closure, OCR weights, ROBOT JAR,
   and a disposable PostgreSQL schema. Run the unpacked tour in two fresh kernels against
   the same disposable workspace. Compare independent releases, earlier and revised
   dependency pins, and the committed publication audit.
4. Run the [manual manufacturing handoff](../examples/notebooks/README.md#manufacturing-and-independent-hosts)
   against the unpacked tour and installed wheel. Confirm the earlier pressure maximum of
   four and the reviewed maximum of five. The FDE, ERP and GraphRAG hosts load the delivered
   files after the temporary producer workspace is removed.
5. Consult the [conformance report](v1-conformance.md) for actual failure, recovery,
   resource and security fixtures. Code demonstrating the business workflow lives in the
   guide and notebook.

## Gateway evidence

The initial 1.0.0 candidate ran the full English Act and guidance through LiteLLM and Luna.
Both sources produced typed proposals and the fixture reviewer published two independently
readable releases. The automatic Act comparison matched one of seven expected lookup names
and citation pages. The semantic review remains part of the final session.

The rebuilt wheel passed the live page-46 smoke test with 1,355 input and 95 output tokens.
The conservative reservation for a second full-corpus call exceeded the remaining shared
allowance, so the budget guard declined the attempt before calling the provider. The rebuilt
wheel replayed both recorded responses against matching source, prompt and schema hashes
and independently reloaded both reviewed releases. The campaign accounts for 438,457 input
and 10,753 output tokens across nine attempts. The [sanitized receipt](../examples/notebooks/fixtures/discovery-luna-release-candidate.json)
records the wheel digest, exact run boundaries and provider provenance.

## Compatibility contract

| Contract | Frozen version and scope |
| --- | --- |
| Python SDK | Domain Kernel 1.0.0 on Python 3.13 and 3.14. Package-root exports, keyword-only contracts and the `py.typed` marker are checked. |
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

1. Begin in a new workspace after provisioning. Time the first publication and independent
   reload against the ten-minute newcomer target. Check the instructions and recorded approval.
2. Run the C4 and C6–C7 practice tasks. Observe incorrect-answer feedback, hints, resets,
   changed-intent preview, and a name lookup in the delivered bundle. Use the E10 keyboard
   path and code fallback in VS Code and compare the saved reading version. Note any hosted
   frontend used and the behavior observed.
3. Review the [frozen Act expectations](../examples/notebooks/fixtures/discovery-expectations.json)
   and [guidance update rubric](../examples/notebooks/fixtures/discovery-update-expectations.json)
   before opening the private candidate provider receipt. Compare meanings, relationship directions,
   citations, mappings, omissions and review effort. Record the semantic judgment separately from
   the replay and automatically checked lookup/page results.
4. Run the [credentialed S3 and SharePoint recipes](../examples/notebooks/README.md#s3-and-sharepoint)
   once the host bindings can be configured. Compare exact selected items, byte hashes and
   revisions, then verify delivery with the output binding and its own credentials.

Record those results in the acceptance PR. The [roadmap](../ROADMAP.md#v1-completion-checklist)
tracks the combined criteria. Tagging and distribution publication follow the separate release process.
