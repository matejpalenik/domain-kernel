# Discover a model from a document

Open the [recruitment discovery notebook](../examples/notebooks/document-discovery.ipynb) to see what a developer can recover from the complete English AI Act. Its saved output shows the real run. The [graph and source citations](evidence/recruitment-document-discovery.md) cover every proposal, including disconnected concepts.

From the repository root, install the optional integrations, put `OPENAI_API_KEY` in the root `.env`, select the project kernel, and choose **Run All**.

```sh
uv sync --locked --group notebook --extra documents --extra discovery-workflow --extra inference
```

A first live run downloads the pinned publisher PDF as needed and uses paid Luna calls for extraction, omission checks, verification, repair and relationship review. The example limits parallel requests and reserves input and output tokens in its local budget ledger. Keep the same workspace and operation key to reopen the reviewed cases with the SDK. The notebook prints the number of new provider attempts.

## Use your own source

Configure `ClientIntegrations(format_parsers={"pdf": DoclingParser.for_discovery()})` when constructing your client. This captures the original page text and Docling's native hybrid chunks for that revision. The default tokenizer uses `o200k_base` and a 2,048-token chunk target. Use `chunking="hierarchical"` to keep Docling's document hierarchy, or pass a Docling chunker with a stable `chunker_fingerprint` identifying its implementation and settings. Change the parser configuration before ingesting the source. Preserve an addressable original and enable extracted-text retention.

Configure `LangGraphDiscoveryGateway(gateway=your_gateway, directory=private_directory, profile=provider_profile)` as the client's model gateway. Include endpoint, model and inference settings in the profile. Put your business scope in the model description and pass the revision to the public discovery API.

```python
run = await model.discover(
    sources=[capture.revision],
    actor=reader,
    idempotency_key="discover-policy-revision-1",
)
cases = [case async for case in model.iter_review_cases(run_id=run.id)]
```

A proposal is ready for a reviewer. Every retained claim, condition and exception links to evidence. The private report also records alternative formulations, failed checks and disconnected components. The SDK carries qualifications in proposal meanings and citations. The report retains their structure. Human review and publication remain explicit SDK operations.

Optionally supply `mention_detector=NamedEntityHints(predict=predict, profile="local-model-v1")` to the staged gateway. A GLiNER-compatible local predictor receives passage text and the configured label list. Its exact-span suggestions feed the omission check. All eligible passages still go through extraction. The recorded AI Act run used the standard extraction and omission stages without an NER model.

## Replay and diagnose

To rerun the stages locally from an existing journal, with no provider or API key configured:

```sh
uv run --locked --no-sync python -m examples.notebooks.document_discovery --offline
```

This command needs the previously verified PDF, SDK workspace and stage journal. The example stores the SQLite workspace, journal, checkpoints, audit reports and budget under `local/staged-recruitment-discovery/`. A fresh SDK extraction reconstructs the draft using recorded responses. Each completed stage also has a resumable checkpoint. An unknown paid-call outcome or missing receipt stops replay and identifies the missing evidence.

Inspect `failure.issue.path`, `failure.code` and `failure.message` for a rejected response. For example, an unresolvable target identifies the relationship index and the `target` field. You can also wrap a conventional gateway in `LocalReplayGateway`, then reopen the same journal and profile with the provider omitted to inspect the response that failed validation.

Use a private directory per tenant. The journal, reports and checkpoints may contain source text and personal data. Setting `retain_responses=False` skips new raw-response and checkpoint payloads and prevents local reconstruction. It leaves existing retained files and SDK evidence under the host's retention policy. Interrupted provider attempts stay reserved until their billing and outcome can be reconciled.
