# Discover a model from documents

`Model.discover()` drafts a reusable domain model from exact, ingested source
revisions. It saves the draft and opens review cases. It does not approve
definitions or publish a model.

## Configure a source and provider

Install the `documents` extra for Docling and the `inference` extra for LiteLLM.
Use `PDF`, `Word`, `Excel` or `CSV` for those formats. For other supported
formats, use an explicit `DocumentFormat` when the extension is ambiguous.
The [Docling input catalog](https://docling-project.github.io/docling/usage/supported_formats/)
describes additional parser requirements.

Enable extracted-text retention or keep the original accessible so the SDK
can reopen evidence. Ingest each source before discovering. The
[recruitment notebook](../examples/notebooks/document-discovery.ipynb) shows
configuration and ingestion of a pinned publisher PDF.

Configure `LiteLLMGateway` with your provider, model and credentials. You can
use it directly or wrap it in `LangGraphDiscoveryGateway` to retain private,
exact stage receipts and route individual stages to different providers. Use
an owner-only journal directory and stable provider profiles that include
the endpoint, model and inference settings. No discovery opt-in is needed.

## Draft and inspect

```python
run = await model.discover(
    actor="user:model-editor",
    sources=[capture.revision],
    idempotency_key="discover-policy-revision-1",
)
cases = [case async for case in model.iter_review_cases(run_id=run.id)]
for case in cases:
    for citation in case.evidence:
        resolved = await project.get_evidence(evidence=citation)
        print(resolved.excerpt)
for failure in run.failures:
    print(failure.code, failure.message)
```

A plain call uses the model description as its purpose. Pass
`SchemaDiscoveryOptions` to supply competency questions, source context
such as roles and effective dates, or an as-of date. Use
`additional_instructions` or `prompt_override` to focus the model. These
inputs change the task, not the workflow.

Short packets go straight to drafting. Long packets first receive an
orientation pass to locate relevant passages and records. The SDK binds
candidate meanings to issued source spans and checks ordered roles against
the source. It reviews the draft against the whole question set, with at most
one targeted follow-up for a gap grounded in the source. If a reference pack
is attached, the SDK compares meanings after drafting. A mapping suggestion
does not change the local graph or approve correspondence. See the
[workflow design](../ARCHITECTURE.md#whole-question-discovery-workflow) for the
transaction boundary and custom gateway contract.

Discovery defaults to 128 review items, a 512 KiB response limit, and up to
600 seconds per stage within a 2,400-second inference budget. Drafting and
orientation can use up to four attempts. Each review pass gets one attempt.
Set stricter limits in `InferencePolicy` or the staged gateway; the provider
may enforce its own limits. The SDK does not choose a provider or model.

## Reopen or resume

Use the same revisions, configuration and operation key to reopen the result.
A failure can coexist with a reviewable draft. Inspect `run.failures` and use
`model.resume_discovery(actor=reader, run_id=run.id)` to retry unfinished work
in the same workspace. A staged gateway can replay retained requests without
provider access when configured with `gateway=None` and the original profiles.
It does not send missing requests while offline.

If source coverage is deferred, inspect `project.profile_source(...)` and
complete the capture before resuming. No pre-v23 discovery run migration is
provided.

Use `model.extract_proposals(...)` for an independent proposal draft without
a review queue. Use `model.propose_alignment(...)` explicitly to reconcile
that draft and open review. These standalone calls do not run whole-question
discovery or inherit its limits.

See the [v23 benchmark results and replay instructions](evidence/discovery-v23.md)
for what was measured and what was not.
