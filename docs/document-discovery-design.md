# Document discovery with Docling and LangGraph

**Proposed design.** A developer supplies a source revision and a business scope. They receive a reviewable draft of domain concepts, directed relationships and qualified claims, with evidence they can reopen. A reader can see which parts of the source were processed, what remains uncertain and what a reviewer ultimately approved.

The baseline sends retained passages to the configured gateway in one request. The optional LangGraph gateway now runs the stages described below behind the same SDK entry point. The evaluation and deployment criteria below remain targets. [Run and replay the implementation](document-discovery.md) · [Inspect the full-PDF results and limitations](evidence/recruitment-document-discovery.md)

In the [full-PDF notebook run](../examples/notebooks/VALIDATION.md), the provider returned a response but validation rejected it. No draft was created. The SDK retained a generic diagnostic. The target executor must distinguish an invalid endpoint, citation, duplicate name, out-of-range value and truncated response, and identify the affected claim or field. With retention enabled, preserve a restricted-access response artifact so operators can replay decoding without paying for new inference. With retention disabled, preserve the diagnostic and fingerprint.

## SDK experience and ownership

Keep the public entry point:

```python
run = await model.discover(
    sources=[revision],
    actor=author,
    idempotency_key="discover-source-revision",
)
```

The model description supplies the business scope. The existing gateway supplies credentials, endpoint and model. A source-agnostic extraction policy supplies the task and output contract. The caller can still provide discovery instructions. A caller's prompt override applies to extraction. Validators, evidence resolution and publication decisions retain their own contracts.

Implement the executor as an optional LangGraph integration behind the discovery application boundary. Use a typed `StateGraph` for explicit transitions and bounded parallel work. Each inference node calls the configured `ModelGateway`, including LiteLLM. Keep LangGraph, model clients and Docling imports in adapters. Manual authoring remains available on a core-only install. An opt-in deployment may use LangChain utilities where they add value. The notebook needs only the existing SDK calls and configuration. [LangGraph workflows](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

## Source to review

| Stage | Input and responsibility | Durable output |
| --- | --- | --- |
| Capture and parse | Pin the source bytes and preserve native document structure. Detect missing text, unreadable pages, broken reading order and unsupported formats. Request OCR or an appropriate parser when needed. | Revision, parser fingerprint, structure and locators, coverage findings |
| Chunk | Run the configured chunker on that structure. Add headings and table context for inference. Keep the original passage separately addressable. | Ordered chunk manifest, each chunk's source spans and token count |
| Extract | Fan out bounded batches. Give Luna the business scope, an approved terminology summary when relevant, and the identified passages. Ask for atomic claims, typed mentions, directed predicates and evidence. Allow an empty result. | Schema-validated local drafts with chunk-local IDs and cited spans |
| Reconcile | Resolve aliases across chunks, retain homonyms, and seek definitions and exceptions at referenced locations. Resolve both endpoints of each relationship. Keep conflicts visible. | Document-level concept candidates, claims and provenance for every merge |
| Verify | Check lineage in code. Ask a model to test each claim against its passages and relevant surrounding or referenced text. For disputed claims allow a bounded lookup and correction, then record the verdict. | Per-claim evidence, support verdict and proposed repair, preserving the original draft |
| Check omissions | Read source sections against the assembled draft. Check unmatched terms, unrepresented actors or actions and referenced qualifications. Send each proposed addition through verification. | Coverage by section, supported additions and remaining review findings |
| Hand off | Materialize proposals using the SDK's existing explicit review path. Surface unresolved references, low-quality captures, partial support and disconnected graph components. | Review cases and run summary. A reviewer decides which definitions and rules enter a publication. |

Empty results, unreadable sections, budget exhaustion and interrupted work have distinct outcomes. Every eligible passage gets a recorded disposition. A graph can contain isolated concepts. Require resolvable endpoints for every proposed edge and let a reviewer decide whether separate components belong together.

## Docling chunking defaults and overrides

Use **`HybridChunker` by default for Docling documents**. It starts from the hierarchy in the `DoclingDocument`, splits oversized chunks using a tokenizer and can merge adjacent peers sharing heading and caption context. This is structural chunking with a token budget. A thematic shift inside a poorly structured paragraph may still need review. Feed the native document to the chunker before the current adapter flattens it into page text. Existing retained page evidence should stay addressable. Reparse older captures from their pinned originals when structured input is needed. [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/)

Expose a keyword-only chunker choice on the optional Docling integration. For example, the proposed `DoclingParser(chunker=HierarchicalChunker())` would select document hierarchy alone. Accept Docling's `BaseChunker` interface for other supported choices or a host implementation. Record the actual chunker, tokenizer, versions, token limit and peer-merging settings. Require a stable implementation fingerprint for custom chunkers. Apply the gateway's request limit after contextualization, allowing room for instructions, schema and response. Oversized atomic items receive an explicit fallback or a visible finding.

Preserve item references, physical page and available offsets or bounding boxes, heading ancestry and table cell or row references. Repeated headers and context copied from other sections point back to their original spans. Cross-references may cross chunk boundaries or revisions. Follow them only into the supplied, pinned corpus and record unresolved targets. Prefer native sheet, row, column and cell-range locators for spreadsheets, heading/paragraph locators for text, and page/region locators for PDFs. Report supported formats and capture quality explicitly.

## Claims, conditions and exceptions

Introduce a **versioned internal extraction schema**. Each atomic claim identifies its subject, predicate, object or other roles, modality when explicit, and evidence spans. Attach two structured collections to that claim:

| Field | Meaning | Example from a neutral operating procedure |
| --- | --- | --- |
| `conditions` | What must be true for this claim to apply | A supervisor approves a return **when its value exceeds the threshold**. |
| `exceptions` | A stated carve-out that changes the base claim | The approval requirement has an exception **for recalled items**. |

Use empty arrays for a supported unconditional claim. Missing, contradictory or unreadable evidence has a separate verification status. For every populated item require the cited passage, source wording and which claim it qualifies. Preserve explicit alternatives and conjunctions. A clause overriding an exception points to that exception. If the grouping or precedence is ambiguous, preserve the passage and ask for review. Test counterexamples that satisfy one alternative, all prerequisites or an override. Do not create graph nodes for incidental phrases.

For multi-party actions retain roles such as actor, object, recipient and destination before deriving a binary edge. Give a mentioned role with an unknown identity a local unresolved reference. Do not invent the missing party. Match mentions to approved meanings by evidence and sense. Keep permanent model IDs under SDK ownership.

Map reviewed qualifications into cited descriptive rules where today's published model can represent them faithfully. Preserve the full extraction artifact. Any interoperable structured qualifier fields on published bundles require a separately versioned wire contract, migration rules and independent-reader tests. Strict structured output enforces shape. Semantic checks still have to establish that conditions, exceptions and directions follow from the source. [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## Named entities and terminology

A conventional recognizer has labels fixed during training. A configurable recognizer such as GLiNER takes entity labels at inference time. Start with an optional, versioned profile with short definitions for **actor or role, organization, artifact or record, process or event, resource, and measure**. Keep values such as identifiers, dates and amounts as anchored mentions when they matter to a claim. A host can extend the profile using its vocabulary and supply approved aliases. Apply phrase or identifier rules where spelling is predictable. [GLiNER](https://aclanthology.org/2024.naacl-long.300/) · [spaCy rule-based matching](https://spacy.io/usage/rule-based-matching)

Pass all eligible source text to extraction. Use span-bearing NER and terminology suggestions as additional candidates during the omission check. A common noun mentioned once can be a business concept. A repeatedly mentioned name can be irrelevant to the scope. Evaluate gains in essential concepts recovered against additional reviewer time and false positives. Enable NER by default only if held-out results justify the cost across domains and languages.

## Verification, scale and recovery

- **Evidence lineage.** Code resolves each cited span to the exact source revision and verifies the quotation against retained text with a recorded normalization rule. Distinguish exact text matches, OCR-backed matches and unresolvable spans. A heading added for context cannot independently support the body of a claim.
- **Semantic support.** Give the verifier the atomic claim, relevant context and linked exceptions. Grade actor, direction, modality, conditions and exceptions as supported, partly supported, contradicted or insufficient. A targeted repair needs new evidence or a narrower statement. A second pass with the same model is correlated evidence. Calibrate it against independent reviewers and route disagreements to review.
- **State and replay.** Key the LangGraph thread to the scoped discovery run. Store artifact references in checkpoints and keep the SDK database authoritative for proposals and review. Fingerprint source revision, scope and approved-context revision, parser, chunk policy, prompts, schemas, NER profile and gateway configuration. Keep successful chunk results across restart and reduce parallel drafts in a stable order. Changing a fingerprint creates new work while earlier evidence remains inspectable. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- **External calls.** Reserve tokens and record attempt identity before dispatch. Persist provider receipt, usage and validated response before advancing the graph. A crash between sending a request and recording its response can leave billing uncertain. Use provider idempotency or reconciliation when available. Otherwise surface that attempt for explicit retry. Enforce per-run cost, timeout, concurrency, backpressure and repair limits. Never hold a database transaction across inference.
- **Privacy and observability.** Scope access to documents, checkpoints and caches to the owning project and tenant. Treat source text as data and allow extractors only the tools and pinned revisions they need. Keep credentials, raw document text and sensitive mentions out of ordinary logs. Expose stage progress, coverage, validation failures, latency, token usage and reviewer dispositions. Apply retention and deletion policies to derived artifacts as well as source material.

## Criteria for switching the SDK default

1. Freeze a held-out set by document family across policies, operating manuals, forms, spreadsheets, scanned documents and irrelevant inputs. Have independent reviewers adjudicate essential concepts, acceptable aliases, directional claims, qualifiers and evidence before revealing system outputs. Keep the recruitment example for regression testing.
2. Compare the single-call default, hybrid chunks with reconciliation, the verified workflow and the optional NER pass on the same sources, scope and budget. Measure concept precision and recall, correct endpoint/predicate/direction, qualifier scope and polarity, citation support and completeness, correct abstention, reviewer time, latency and cost. Set acceptance thresholds before seeing results. Use ACTER for domain terms, Re-DocRED for document-level relations and ContractNLI for evidence-backed qualification and abstention. [ACTER](https://lt3.ugent.be/publications/annotated-corpora-for-term-extraction-research-act/) · [Re-DocRED](https://aclanthology.org/2022.emnlp-main.580/) · [ContractNLI](https://aclanthology.org/2021.findings-emnlp.164/) · [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
3. Exercise cross-chunk aliases and exceptions, parse degradation, provider truncation, cancellation, duplicate deliveries, concurrent resumes and a lost provider response. Require zero dangling endpoints or unresolvable citations in verified proposals. Show incomplete runs explicitly. Demonstrate that completed work replays without another paid request.
4. Introduce the optional workflow alongside the single-call baseline. Compare in shadow runs on authorized data, inspect failures by document type, and change the default once the quality, cost and recovery criteria pass. Roll back by selecting the previous versioned executor for new runs.
