# Benchmarking reusable domain-model discovery

**Recommendation.** Make real-document, reference-blind schema discovery the primary
test. Use published ontologies such as FIBO in a separate alignment track, and
reverse-design synthetic packets for controlled challenges, not as evidence of
real-world discovery quality. Gate releases on what downstream modeling consumers
can use and verify, with uncertainty and total cost reported alongside quality.
This is a proposed protocol, not a benchmark result or a claim of industry-wide
coverage. The existing [EU procurement protocol](../../benchmarks/README.md#eu-procurement)
is the starting point for a first vertical, not a substitute for fresh evidence.

## 1. Define the claim and what counts

**Target use.** Given a packet of original English-language enterprise documents,
produce a reusable, reviewable representation of what the documents establish:
concepts and distinctions, typed relationships with ordered roles, and rules with
their scope, conditions and exceptions. A *domain model* here is this scoped
representation; it need not use a formal ontology language. An *ontology* adds
explicit, machine-interpretable definitions and axioms under declared semantics.
An exported vocabulary or a graph of named instances alone is not evidence of
ontology discovery. This usage is consistent with [Gruber's definition of an
ontology as a specification of a shared representational vocabulary](https://tomgruber.org/writing/ontolingua-kaj-1993/);
the distinction is an operational choice for this benchmark. See the
[Domain Kernel glossary](../../GLOSSARY.md#language) for the distinctions
between vocabulary, taxonomy, formal ontology, and domain model.

**Scope: schema discovery only.** The unit of credit is an evidence-backed
reusable meaning: a concept distinction, a relationship with the right roles
and direction, or a scoped rule. A label match or one correctly extracted record
does not establish a reusable meaning. **Instance population**, the extraction
and recording of facts about particular entities or events, is outside the current
SDK and this benchmark. Independently authored example records are test inputs
for the grader, not records the SDK is expected to produce.

The **packet** is the input and paired evaluation unit: one document or a frozen
set of related documents needed to understand a case. Treat the highest shared
lineage as a single sampling and inference unit; justify any assumption that such
groups are independent. Documents, spans, claims, queries and repeats within a
group do not increase the independent sample size. Define intended deployment
coverage, exclusions, source precedence and materially distinct claims before
collection.

For each expected meaning, record a precise witness (page and region, table cell,
worksheet and cell, or stable section and excerpt), authority and dates, ordered
roles, conditions, scope and why the witness is sufficient. Mark it **required**,
**permissible but optional**, or **not inferable from the packet**; separately mark
explicit contradictions and unresolved ambiguity. Do not ask a system to recover
an entire external reference from a few documents. Do not infer universal
cardinality, class disjointness, legal applicability, or default policy from one
example or silence. A correct abstention on a non-observable item is not a missed
required meaning; a confident invention is an unsupported output. Retain an
authority-conflict test where neither statement may silently replace the other.

Accept equivalent decompositions, inverse relations used correctly, aliases,
reification and local extensions when they preserve meaning, scope and executable
behavior. Specify what would disqualify each alternative (for example, a class
merge that loses a role distinction). [Noy and McGuinness, *Ontology Development
101*](https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html),
explicitly say there is no one correct model and that the appropriate choice
depends on intended use; they also treat scope, reuse and instance creation as
distinct decisions. Do not grade by exact labels, IRIs or graph edit distance
except in a separately named identity or serialization check.

## 2. Run three tracks; do not pool their scores

| Track | Inputs and protocol | Permitted conclusion |
| --- | --- | --- |
| **A. Real, open discovery (primary)** | Original, independently selected business documents. Give every system the same bytes, declared use, caller questions and any neutral scope notes. Withhold the target ontology, answer key, reference mappings and grader-only checks; block retrieval into answer material. Select by business scenario and document coverage, not by resemblance to a reference. | How well these configurations discover reusable meanings supported by these English documents. |
| **B. Reference-guided alignment** | On a matched set of real packets, compare the same configuration with and without a fixed reference bundle. Give both arms the same task, source bytes and operating envelope. Freeze reference release/commit, modules, imports, bytes and hashes, and exactly what each arm can see. Score evidence-grounded coverage, mapping type (exact, broader, narrower, related or no match), justified extensions and mapping errors. | What supplying this particular reference changes, and how well outputs align to it. A correct mapping does not earn discovery credit by itself. |
| **C. Controlled synthetic challenge** | Start from stipulated truths and counterexamples, optionally informed by a reference. Commission independently rendered documents, not just rendered ontology labels; preserve truth manifests and provenance. Use matched pairs that change one factor at a time, such as paraphrase, unfamiliar names, irrelevant passages, version drift, exceptions, negation, layout degradation, contradictory annexes, or locally valid but out-of-reference concepts. Keep generators, templates and variants grouped and out of development. | Sensitivity to a known perturbation or failure mode. Do not pool this with real-document measures or report its error rate as a natural prevalence. |

[EDM Council's FIBO specification](https://spec.edmcouncil.org/fibo/) and
[publisher repository](https://github.com/edmcouncil/fibo) identify FIBO as an
OWL ontology of financial business concepts. It is suitable as a reusable
reference for a carefully scoped finance study; it is not the answer key to
every finance document. Select and pin a [published release](https://github.com/edmcouncil/fibo/releases),
not a moving branch. It is reasonable to find independently authored real
documents for **B** that exercise selected FIBO modules. If a sample of real
documents is deliberately enriched for a target axiom, label it a targeted real
cohort and report its results separately from the primary discovery sample.
Designing documents to express the axiom instead tests recovery of stipulated
content, as in **C**. In either case, include
reference-absent and unsupported-reference controls; in guided runs, importing a
correct but unwitnessed term is not successful extraction. Compare plain versus
paraphrased and public versus fresh material where possible, and use a no-document
arm to diagnose prior knowledge or memorization. None of these checks proves
absence of pretraining exposure. If measuring latent alignment in the unguided
arm, map its frozen outputs with the same blinded rule used for the guided arm
and keep post-hoc alignment separate from what the system natively delivered.

## 3. Freeze the evaluation before inference

1. **Describe the sampling frame.** For each stratum, record eligible sources,
   dates, language, authority and retrieval procedure, inclusion/exclusion rules,
   and a probability sample where feasible. If public availability or rights
   dictate purposive selection, report the selection process, missing cells and
   limits. Target recent and rights-cleared non-public sources where possible,
   but keep those strata distinct. Track exact hashes and check near-duplicates,
   shared authors, authority, procedural lineage, derived data, boilerplate and
   common templates. Assign connected near-duplicate or reuse groups to one split;
   reserve unseen authorities/templates or a later time window explicitly when
   making transfer claims. No chunk, translation, reissue, derivative or
   synthetic rewrite may cross splits. [Roberts et al.](https://doi.org/10.1111/ecog.02881)
   study blocking for structured data; the document grouping here is an
   application of the dependence principle, not a result of their study.
2. **Seal development and test separately.** Build and calibrate the rubric, keys
   and runner on development groups. An evaluator who is not tuning the SDK holds
   the locked inputs and sealed keys; the inference runner gets only the appropriate
   inputs after the candidate, baselines, configuration and analysis are frozen.
   Hash and timestamp the split manifest, case/fixture versions, keys, evaluator
   code, metric definitions, exclusions, gates and stopping rule. Audit access
   and check prompts, retrieval, caches, few-shot examples and tool inputs for
   leakage. Known public material cannot be certified unseen by a provider:
   distinguish *sealed from developers* from *potentially exposed in training*.
   Report suspected overlap rather than silently deleting poor or good cases.
   After unblinding, a set is suitable for regression and audit, not for fresh
   claims about a system tuned on its results. Refresh by sampling new groups and
   keep a versioned history. [Dwork et al.](https://arxiv.org/html/1506.02629v2)
   demonstrate the risk of adaptive reuse of an ordinary holdout.
3. **Author the key from source and use case first.** Before any held-out output
   exists, a domain expert and an ontology engineer sign the scoped meanings,
   witness policy, known alternatives, negative conditions, criticality and
   executable fixture expectations. Use official underlying data or a reference
   only as a documented cross-check: a fact visible solely there is not observable
   to the inference arm. Keep authors/key custody independent of prompt tuning.
4. **Grade independently and blind.** Two qualified reviewers score the same
   anonymized, shuffled outputs independently, with source, signed key and rubric,
   but no system identity, cost, paired output context or other review. Calibrate
   on shared development examples and freeze examples/rules; a third adjudicator
   resolves discordant ratings and records why. Report pre-adjudication agreement
   by criterion and stratum (counts by label, raw agreement and a prespecified
   chance-corrected statistic such as nominal [Krippendorff's alpha](https://repository.upenn.edu/entities/publication/034a6030-c584-4d14-9d3d-7b7e8d16df20),
   where estimable). Review critical cases even if both grades agree. Use a
   prespecified, system-blind rule for supported novel outputs or previously
   unlisted equivalent encodings and apply it across arms. Credit newly
   recognized equivalents against the existing meaning; a genuinely new
   supported meaning may earn precision credit under the evidence rubric but
   does not enlarge the primary recall denominator. Log key defects and disclose
   sensitivity or invalidate/replace a compromised version. Any automated judge
   is a separately calibrated diagnostic, not the authority for acceptance.

## 4. Competency questions are executable tests

[Grüninger and Fox's original competency-question work](https://link.springer.com/chapter/10.1007/978-0-387-34847-6_3)
uses questions to characterize what an ontology must be able to represent and
solve, and to guide development. [Peroni's SAMOD](https://essepuntato.it/samod/)
ties motivating scenarios, informal questions and exemplary answers to a formal
model, example data and queries, with tests through iterative refactoring.
Applying those ideas, write the test from the downstream task before writing the
gold model. For each question keep:

- The user-facing question, required distinctions, reference witness, expected
  bindings or Boolean, and a positive fixture plus a minimally different
  counterexample. Include explicit scope/exception, wrong-direction and unknown
  cases. Separate caller questions (visible, as they would be in a real SDK
  call) from grader-only checks. A caller can ask how to represent the winning
  supplier without supplying the answer or the intended class structure.
  Freeze the same caller brief for each arm, and withhold the executable
  queries, fixtures, expected answers and any supplementary grader questions.
- A **schema-capability test**: instantiate the candidate schema with independently
  authored, previously unseen records, and execute expected queries or
  entailments. A frozen adapter or blinded equivalence mapping may translate
  representation, but must not supply missing assertions or rules. Keep mapping
  edits, reviewer minutes and exact fixture outcomes. An output that cannot be
  instantiated, queried or checked is not a pass. Verify a second scenario with
  different actors and values to detect hard-coded records.
- For a **constraint test**, validate independently authored conforming and
  intentionally nonconforming graphs against the candidate's declared rule.
  This checks whether the discovered rule preserves the distinction, not
  whether the SDK can find and populate real records. Nonconformance is not
  evidence of an ontology inconsistency unless tested as such.

**Trace each question to its competency requirements.** Adapt the useful part of
[Kurt Cagle's question–lemma–test pattern](https://ontologist.substack.com/p/competency-questions-lemmas-and-shapes)
in the benchmark key, not as a new SDK object. For each requirement record
the reusable distinction, its source witness and applicability, the linked
check or documented reason it needs manual review, and the failure severity
in the rubric. Label fixture assumptions separately. For example, “the data
includes a current award status” may be a test precondition; it does not
establish “every award record must have a status” as a discovered business rule.
Source obligation, fixture completeness, and release criticality are distinct.
Do not automatically turn `MUST`/`SHOULD`/`MAY` into SHACL severities. Use queries
for expected answers and shapes for expressible validation obligations.

[W3C SPARQL 1.1](https://www.w3.org/TR/sparql11-query/#ask) specifies `ASK` for
pattern matches and `SELECT` for result bindings; pin dataset, entailment regime,
query engine and expected results. `ASK false` for an unmatched pattern is not a
proof of negation under OWL's [open-world interpretation](https://www.w3.org/TR/owl2-primer/).
Use [OWL 2 Direct Semantics](https://www.w3.org/TR/owl2-direct-semantics/#Inference_Problems)
for consistency, satisfiability and positive entailments or explicit negatives
where they are warranted, and [W3C SHACL](https://www.w3.org/TR/shacl/#validation-report)
for declared graph validation, recording expected violation paths/severities where
relevant. Pin imports, reasoner, entailment and SHACL settings. Declare which
tests are applicable if the SDK produces a model rather than OWL; a harness may
translate syntax, but not upgrade expressiveness by inserting missing domain
rules. Do not report formal ontology acceptance without formal tests.

**Worked example (authored, not a scored packet).** Ask “Who won this procedure?”
The source rule says a recorded selection identifies the winner only once the
decision is final. The candidate schema must support both the selection and its
status, and distinguish selection from participation. After checking those
meanings against the source, bind their corresponding terms to this fixture:

```turtle
@prefix ex: <urn:example:> .
ex:decision ex:status ex:Final ;
    ex:recordsSelection ex:supplierA ;
    ex:hasBidder ex:supplierA, ex:supplierB .
```

```sparql
PREFIX ex: <urn:example:>
SELECT DISTINCT ?supplier WHERE {
  ex:decision ex:status ex:Final ;
              ex:recordsSelection ?supplier .
}
```

The positive case returns only `urn:example:supplierA`. For the counterexample,
change only `ex:Final` to `ex:Pending`; expect no bindings, not proof the supplier
lost. Dropping the status check fails the counterexample; substituting
`ex:hasBidder` fails the positive case. If the data contract separately requires
exactly one recorded winner for final single-award decisions, use SHACL to test
conformance and the expected missing-value violation.

## 5. Compare entire systems at the same finish line

Use original bytes, from parsing/OCR and normalization through extraction,
verification, reconciliation and durable handoff. Record real scanned PDFs,
tables, annexes, form and report variations and packet sizes; include other
formats only where they matter to the target. Run a fixed text/parser control
on the same sources to diagnose whether losses are upstream; do not substitute
it for the primary run. Freeze configurations and case inputs. Compare the
candidate on the same packets against both the last SDK release and a
single-call baseline using the candidate's underlying model. Keep the declared
inputs, task, and handoff boundary fixed. Record budget or context failures
rather than silently changing the inputs for an arm. Use draft or verification
ablations for diagnosis. The signed human key is the target, not a system
baseline. If describing manual effort, measure a
separate human-only workflow. Evaluate no-document and matched reference arms
as controls, not primary competitors. Predefine equal scope, permitted resources
and retry/repair budgets; report both an automated completion and an independently
reviewed usable handoff when claiming the latter. Never compare one arm's draft
to another arm at reviewed completion.

Report eligible packets, delivered packets, and reason-coded partials, abstentions,
timeouts, parse failures, retries, truncations and exclusions. Keep started
failures in the denominator for completion and coverage; missing required
meanings are misses. Use one-to-one semantic-unit matching, record duplicate
handling, and score support/precision over emitted units (including incorrect,
unsupported or materially incomplete units); report recall over required
observable meanings. Do not mark no output as perfect precision: show undefined
denominators and failure coverage. Show query and validation outcomes and
category-specific errors alongside claim scores.

Report **usable drafts** and **automated review completion** separately. An
unfinished automated review can yield a usable draft if the draft is available
for review, independent grading finds no critical defect or missing observable
critical meaning, and every applicable critical check passes. It still counts
as unfinished review. A missing draft, ungraded critical requirement or
unexecuted critical check is not a usable handoff. Include unsuccessful
attempts in the denominator for both rates.

For cost, publish provider model/revision, dates and tariffs, input/cached/output
and charged reasoning usage as available, tool/OCR and compute costs, retries and
failed work, and active human review/rework time. Measure ingestion-to-handoff
wall-clock time, time to usable result and queue delays, with workload,
hardware, concurrency, cache state and rate limits declared. Pair or interleave
arms to avoid time-of-day/provider confounding; use repeats on a prespecified
subset to assess run variability. Report total and per attempted/usable packet
cost, as well as throughput and latency distribution at specified loads and caps;
give uncertainty for latency summaries and show timeouts separately (do not
average only fast successes and call it system latency). Label thin tail
estimates exploratory. Account for annotation and judging as benchmark cost,
distinct from production review. A cheaper candidate wins only at comparable
completion and acceptable quality; show trade-offs rather than a single combined
score.

## 6. Size and gate the study before looking at test results

- **Plan for precision and a meaningful comparison.** Choose the primary
  estimands and fixed stratum weights to match the declared use, or label a
  balanced design as such. Use the development pilot and modeler tolerances
  to set the numerical quality, usability, completion, cost, and latency
  gates before opening the holdout. The current procurement point thresholds
  are starting context, not preapproved floors for the new study.
  From development data, estimate packet sizes,
  within-lineage dependence, between-lineage and paired-arm variability, and
  annotation error. Specify a decision-relevant confidence interval width for
  absolute performance and either a minimum worthwhile paired improvement or
  a defensible non-inferiority margin for a cheaper candidate. Simulate planned
  group sizes, strata, paired outcomes and missingness across plausible values;
  size for interval width and probability of the intended decision, not for an
  arbitrary number of documents. [Green and MacLeod](https://besjournals.onlinelibrary.wiley.com/doi/10.1111/2041-210X.12504)
  demonstrate prospective simulation-based power for mixed models; the simulation
  for this study should reproduce its own sampling and scoring, not import their
  model uncritically. If the resources cannot support the prespecified precision
  or adequately cover important strata, narrow the claim or call the study a
  pilot.
- **Keep pairing and clustering in the inference.** Report effect sizes and
  intervals for absolute rates and paired differences by stratum, plus the
  preweighted result, macro packet summaries and micro counts with denominators.
  Where supported, resample whole independent lineage groups within strata,
  preserving packet pairs, and recompute the metrics; respect the sampling
  design and vet interval behavior in the planning simulation. If a group spans
  strata, keep it intact rather than resampling its parts independently. With too
  few groups or degenerate intervals, publish counts, packet outcomes and
  limitations instead of precise-looking confirmation. [Field and Welsh](https://researchportalplus.anu.edu.au/en/publications/bootstrapping-clustered-data/)
  show why bootstrap behavior depends on the cluster model; [Cameron and
  Miller](https://jhr.uwpress.org/content/50/2/317) describe how ignoring cluster
  correlation can overstate precision. Declare primary versus exploratory
  comparisons and how multiplicity will be handled for advertised claims.
- **Fail closed.** Before unsealing, set numeric floors, margin(s), scope,
  completion, review budget, latency and cost caps with intended consumers; these
  are operational choices, not literature constants. For quality and any
  non-inferiority claim require prespecified lower confidence bounds to meet
  their limits; for critical cost/latency caps use a prespecified upper bound on
  the relevant metric. Require all scoped critical fixtures to be executed and
  **zero observed critical defects** (including a missing observable critical
  meaning, wrong party or role, reversal of a binding rule or condition, or an
  invented citation used for a material assertion, as defined by the rubric).
  A correct abstention on genuinely insufficient evidence is not a critical
  omission; abstaining instead of preserving an observable critical meaning
  does not pass. Report omissions, incorrect assertions and unexecuted checks
  separately. Missing reviews or tests, questionable independence,
  failed integrity checks, or intervals too wide to make the decision are not
  passes. Record failure separately from insufficient evidence. A failure or
  inconclusive result triggers investigation and a fresh sealed evaluation
  before release for that scope. Report all attempts; do not sample repeatedly
  until one passes under a fixed-sample decision rule.

Zero observed critical defects is a gate, not a reliability guarantee. For zero
events among `n` independently sampled, comparable trials under a common
Bernoulli rate, the exact one-sided 95% upper limit is `1 − 0.05^(1/n)`:
it solves `(1 − p)^n = 0.05` (see [NIST's exact binomial confidence
limits](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm)).
For illustration, zero in 24 independent trials yields an upper limit of
about **11.7%**; zero in 299 yields just under **1%**. Neither is a proposed
sample size. Twenty-four related packets, hundreds of queries from those packets,
and curated rare-event stress cases are not interchangeable Bernoulli trials.
If the independent outcome is “any critical defect in a sampled lineage,” its
bound is on that lineage-level event under the stated assumptions, not the
packet-level or industry-wide rate. Report designed challenge results separately
from naturally sampled incidence.

## 7. What Domain Kernel already has

| Evidence | Reuse it for | Do not claim from it |
| --- | --- | --- |
| [EU procurement protocol](../../benchmarks/README.md#eu-procurement) | Frozen and hash-verified captures on 24 packets (6 development, 18 locked), independent key sign-off, blinded adjudication, executable alternatives, and a [native-file runner and direct control](../../benchmarks/procurement_run.py). | A locked result. The local corpus passed input validation; locked validation stopped because there was no independently reviewed key in this checkout. The [current gate](../../benchmarks/procurement_score.py) uses point thresholds; its paired bootstrap compares F1 and is not a confidence-bound acceptance gate. |
| [Whole-question v23 benchmark](discovery-v23.md) | The captured 12 packets are a regression set. The separate 3-packet fix rerun and offline replay check example recovery. | Proposal precision, successful automated handoff or transfer to other industries. The main run mixes 4 real procurement PDF packets with 8 controlled packets, uses one provisional assessor and applies executable checks only to the PDF packets. |

The first held-out claim covers the **pre-human, reviewable model draft**
returned by the SDK from native files. It does not require formal ontology
export. To test whether a modeler can get to an approved model, run a separate
timed review and rework exercise with a fixed budget. Record reviewer additions
and corrections; do not credit those as automatic recovery. Test formal exports
separately when claiming that the SDK produced a formal ontology rather than a
domain model draft.

## 8. Rollout and public reporting

1. **Establish the procurement vertical.** Use the existing
   [procurement design](../../benchmarks/README.md#eu-procurement) to rehearse
   packet manifests, source witness review and positive/negative fixtures. On
   development groups, test rubric agreement, canary failures, cost accounting
   and reproduction. Use those data to size and preregister a locked run.
   Reuse the existing 18 locked packets only if an independent custodian can
   document that the candidate was not tuned on those packets or their
   lineages, and reviewed keys can be frozen before inference. Check source
   reuse and access history, not just manifest hashes. Draw a new holdout
   if either condition cannot be verified.
   Limit the first public performance claim to the English EU procurement
   strata actually evaluated. Do not count prior comparisons or fixed replay
   against known answers as independent confirmations. Add claims for other
   industries only after their own held-out evaluations.
2. **Expand the English sampling matrix.** Use the [UN Statistics Division's
   ISIC Rev. 5](https://unstats.un.org/unsd/classifications/Econ/isic) and its
   [official section and division list](https://unstats.un.org/unsd/classifications/Econ/Download/In%20Text/ISIC_Rev_5_english_structure.csv)
   as a reproducible taxonomy of economic activity. The examples below are
   proposed collection cells, not delivered or representative industry samples.
   Tag the business activity separately from the author (a regulator may
   publish a finance document) and allow secondary codes where justified.
   Within each section, record divisions and independent lineage counts across
   jurisdiction, issuer, time, task and format, including unavailable or
   restricted cells.

   | Proposed activity cell | ISIC section | Example real source types | Reusable distinctions to exercise |
   | --- | --- | --- | --- |
   | Agriculture and extraction | A, B | Service specifications, operating manuals, land or lease policies | Asset or parcel, permitted use, responsibility |
   | Manufacturing and construction | C, F | Specifications, manuals, change orders | Component, tolerance, version and approval |
   | Utilities | D, E | Tariffs, service requirements, service bulletins | Eligibility, thresholds, effective intervals |
   | Transport, storage and commerce | H, G | Carrier rules, service agreements, delivery terms | Custody, delivery, charges and returns |
   | Accommodation and food services | I | Reservation terms, service standards, supplier procedures | Booking, guest entitlement, exception and responsibility |
   | Media, telecommunications and computing | J, K | Service descriptions, SLAs, policy handbooks | Service levels, dependencies, exclusions |
   | Finance and insurance | L | Regulatory filings, prospectuses, policy terms | Instrument or coverage, obligations, exceptions |
   | Real estate | M | Leasing terms, property and maintenance policies | Premises, tenant role, maintenance obligation |
   | Professional and business support services | N, O | Engagement terms, service descriptions, acceptance procedures | Deliverable, approval, access scope or reporting duty |
   | Public administration and procurement | P; tag subject separately | Notices, specifications, award records | Procedure, parties, decisions and authority |
   | Education | Q | Program rules, admissions or transfer policies | Eligibility, equivalence and progression |
   | Health and social work | R | Rights-cleared manuals, reimbursement rules | Provider roles, eligibility, conditions |
   | Arts, sports, recreation and other services | S, T | Participation rules, access terms, service agreements | Membership, entitlement, restriction and exception |

   Maintain one row per section in the actual coverage ledger even where the
   examples above group sectors for brevity. State whether household and
   extraterritorial activities (U and V) are out of scope, planned, or covered.
   For initial transfer, add finance and an operational sector such as
   manufacturing; don't just collect public procurement documents about those
   industries. Keep the samples from operational authors distinct from material
   published by regulators. Report coverage only for cells evaluated so far.

3. **Publish and refresh.** Before results, register the scope, sampling scheme,
   endpoints, decision rules and hashes. With each release publish a
   versioned design and data card, corpus manifest and rights status, code and
   command lines, pinned SDK/parser/model/reference versions, prompts where
   publishable, executable fixtures and rubric from a retired or development
   slice, and aggregate plus rights-cleared packet-level outcomes with uncertainty,
   reviewer agreement, material disagreements, costs, exclusions and failure
   examples. Disclose who selected, authored, evaluated and funded the study.
   Invite an evaluator outside the development team to reproduce the scorecard
   or run a fresh sealed sample before making broader performance claims.
   Release exact originals, keys and raw outputs only with permission
   and after retiring a lockbox; otherwise provide hash-verified source references
   or controlled evaluator access, and spell out which packages are independently
   replayable. Public availability is not permission to redistribute documents,
   excerpts or logs. Remove sensitive material and confirm permission for provider
   processing. Distinguish replay of frozen captures from a new provider run;
   nondeterminism, mutable endpoints, rights and changing upstream documents can
   limit reproduction. Keep English and later multilingual results separate;
   translations stay within a source lineage and cannot stand in for independently
   authored target-language evaluation.
