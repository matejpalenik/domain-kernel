# Interactive preview validation

Checked on 15 November 2026. These results validate the teaching preview, its
fixtures and controls. They do not establish that the planned SDK is implemented.

## Manual recruitment release path

On 17 November 2026, the SDK recipe ran in a freshly provisioned locked Python
3.13 environment with production dependencies. With uv in offline mode after
provisioning, the command took 2.95 seconds. A separate Python consumer reported
purpose limits of two and three for versions `1.0.0` and `1.1.0`.

The notebook acceptance run executes the full tour in a fresh offline kernel.
A second fresh kernel opens the same isolated demo workspace and verifies the
original model ID and both archived hashes. C2 displays the reviewed system
key and bilingual labels. C9 checks the exact locator revision and preserves
the purpose field ID across releases. Tests cover invalid and stale requests.

The time above measures command execution. A human newcomer walkthrough of
environment selection, reading, and the explicit review steps is pending.

## Verified original-source acquisition

C3 and C10 were executed in fresh offline kernels with the four separately provisioned
publisher originals. The SHA-256 pins matched both Official Journal editions, the
Commission guidance and the WEC Europe paper. Direct selection found the English edition.
The recursive reading list retained all four pins, and reopening preserved both language
editions under the same source ID. A fresh run without the originals shows the provisioning
prompt and checks the remaining notebook journey.

## Business shape interchange

The fresh offline kernel and same-workspace replay use the pinned publisher
PDFs and ontology resources. The SDK evidence for each cell is recorded in the
[coverage ledger](coverage.json).

- **C9** independently loads version `1.1.0`, validates the recruitment system
  and provision locator against delivered JSON Schemas, and confirms the
  change to the purpose limit from two to three.
- **E8** loads the reviewed formal RDF/SHACL roles and reports the JSON Schema
  limit for the subclass assertion. The edited LinkML handoff produces a
  pending actor-assignment proposal with fresh identity and the open vocabulary.
- **R1** delivers the duration's JSON Schema and publishes the separately
  reviewed LinkML import. An independent process verifies the imported hour
  edge and schema digest from the delivered bundle. The replay checks that the
  source and imported releases keep the same exact hashes.

[Shape unit tests](../../tests/unit/modeling/test_definition_shapes.py) cover
constructor contracts. The [JSON Schema tests](../../tests/integration/test_json_schema_projection.py)
verify missing, empty, null and bounded data. The
[LinkML tests](../../tests/integration/test_linkml_projection.py) verify native
document loading, requiredness, bounds, unit remapping and exact dependency
resolution. The DK-011 human newcomer walkthrough remains pending.

## Automated checks

- All 21 sections (C1–C10, E1–E10, R1) have planned code, executable preview
  outputs, experiments and ownership across the 43 DK roadmap issues.
- The paired notebook executes its code cells in a fresh Python 3.13 kernel
  with external socket connections blocked. No credentials or original-source
  downloads are required. Execution regenerates the saved static outputs and the
  offline HTML reading version.
- The expanded focused suite checks review gates, acceptance/rejection/correction, blocker
  recovery, repeat submission, explicit reset, stable state, all chapter controls,
  escaped rendering, pairing, source pins and preserved cell IDs after Jupytext sync.
- Planned Python blocks pass syntax and documented-keyword checks. This is not
  receiver/type checking or runtime validation of the future SDK. The examples were
  also compared with the interface guide's builder, review, source, reference,
  publication and projection contracts.
- Saved notebook outputs omit widget state and comm IDs from earlier kernels.
  The reading export contains static diagrams and tables without script loading.
- Ruff, BasedPyright, the existing SDK tests and distribution build were checked
  alongside the focused preview checks. CI provisions notebook tooling separately
  from the SDK job and does not rewrite the notebook or lockfile.
- The completed local suite passed all 304 tests, including 45 notebook unit tests
  and 10 notebook integration tests. SDK coverage was 94%; the coverage configuration
  measures `src/domain_kernel`, not the example helpers.
  Pre-commit's complete fast suite and other hooks passed; BasedPyright reported no
  diagnostics. The distribution build succeeded without changing SDK signatures.

The GitHub workflow has not been run remotely for this change. Local
`gh actions-lock --verify --no-narrow` could not authenticate because no GitHub
token was available. The notebook job reuses the existing full-SHA action references;
no action reference was upgraded.

## Actual VS Code checks

The table below records cumulative observations across the preview's visual passes.
The latest pacing pass rechecked dark-theme execution through all 48 code cells,
C7's conditional-field exercise and free-text lookup task, including explicit answer
checking, incorrect-answer feedback, changed-answer invalidation and successful correction.
The lookup task also worked with Tab navigation and Space to check the answer.
It does not represent a new complete light-theme or screen-reader audit.

Environment: macOS, VS Code 1.145.0, Microsoft Jupyter 2025.9.1, Python extension
2026.10.0, the repository `.venv` (Python 3.13.12), ipykernel 7.4.0 and ipywidgets
8.1.9. The repository folder was opened with the configured root execution directory.

| Check | Observed result |
|---|---|
| Fresh Run All | Completed through R1, with the final code cell executed successfully |
| Evidence selector | Selecting Article 10 updated the passage, exact PDF locator and verification display; the earlier DPV term selection also retained its original identity |
| Model views | Switching from Documentation to Recruitment uses updated the bounded graph and view counts; complete inventories remained available |
| Definition search | Filtering for retention selected the descriptive rule; a no-match search displayed an explicit message; changing it to instructions-for-use restored the matching definition |
| Publication selector | Selecting version 1.0.0 in C10 displayed the first publication instead of the current 1.2.0 snapshot |
| Review decisions | Acceptance, rejection and correction produced their labelled sample impact and applied outcome |
| Explicit submission | Selecting an option did not apply it; preview preceded the separate action |
| Error display | A blank reason displayed an explanatory error and disabled submission |
| Repeat action and reset | Repeated submission did not add another action; reset explicitly cleared the branch |
| Cell rerun | The applied experiment remained visible after rerunning its cell |
| Keyboard | Dropdown selection and Tab/Space submission worked; focused controls were visible |
| Light and dark | Text, tables, SVGs and controls were inspected in Light 2026 and Dark 2026; the original dark theme was restored |
| Static alternatives | Canonical figures, relationship tables, source details and quantities output remained readable independently of controls |
| Article 13 walkthrough | Five stages showed the rejected document merge and the separate qualified-field refinement, with the source and accepted contract side by side |
| Consumer field selector | Keyboard selection changed the displayed field, shape and presence contract without applying a review action |
| Diagram/matrix switch | Selecting Connection matrix replaced the graph with the same directed connections; static matrix and connection tables remained available |
| Progressive detail | Chapter results appeared first; supporting tables, complete inventories and inspector sections expanded explicitly |

An initial test exposed stale widget state in saved outputs, which prompted VS Code
to request older widget modules. The export now removes that state; Run All creates
fresh controls using the installed standard widgets. No CDN download permission was
enabled. Regression coverage checks that saved artifacts do not depend on an old
widget kernel. Broader screen-reader conformance and other notebook frontends have
not been manually certified.

The expanded tour was rerun through code cell 27 after the selector fix. Manual
testing found and corrected a dropdown recovery bug after an empty search; a
regression now covers that transition. The five views, condition inspection,
numbered connection tables and source ledger remain available in static output.
VS Code's kernel restart intermittently remained at “waiting for session idle”
and its toolbar displayed an incomplete Python version. Reload Window followed by
Run All completed successfully; the kernel's actual version is reported by the
environment cell. The separate automated fresh-kernel run does not use that UI.

The preceding visual pass executed the expanded 29-code-cell tour and checked the new
Article 13 cards, read-only consumer, matrix callback and expandable details in
VS Code. It corrected overlapping graph numbers and dark-mode accordion/input/toggle
styling. Light-mode matrix readability and the final dark-mode controls were checked;
the original dark theme was restored. The host renderer still gives widget output
containers a white outer gutter in this VS Code version. Saved static HTML does not
depend on that renderer. A graph regression checks number separation in all five views.
The notebook was closed before regenerating portable outputs to remove live widget IDs.

## Source and simulation boundaries

Acquired Commission guidance, WEC Europe paper, ELI assets, DPV vocabularies and
LOMO documentation have recorded original-byte hashes and locators. The ELI CSV is
an explicitly labelled derivative. Original documents are linked, not redistributed.

The original 2024 Official Journal English and French AI Act PDFs were acquired on
2026-11-15. Their original-byte hashes, 144-page counts, exact source URLs and
verified selected locators are recorded in the acquisition ledger. The selected
English articles/annex and French Article 3 labels were checked against extracted
original PDF text. Core paraphrases no longer carry the earlier failed-download
warning. LOMO's complete ontology/SHACL dependency closure remains unavailable;
its acquired documentation is not presented as an acquired engine input.

The historical preview checks below used simulated parsing, inference, semantic engines,
database operations, review, publication, exports and recovery. Widget experiments change only
their separate local branches. Successful preview checks cannot complete a roadmap
issue or replace the real-SDK milestone acceptance gates.

## Mock-result content review

All 21 sections were reviewed against their planned operations. Result tables now
show concrete IDs, meanings, locators, proposed changes, diagnostics, decisions and
publication versions instead of descriptions of what a future result should contain.
SDK behavior remains simulated; unavailable originals retain their verification warnings.

The review corrected ingestion input counts, the configured output store, process
elements, the three-row profiling input, publication steps and cross-format field
identities. Discovery now displays the accepted model until review; its pending
additions remain in the proposal table. A regression test guards that distinction.

The shared catalogue now supplies the scoped seed (5 definitions), expanded
publication (65 definitions, including 28 relationships) and stakeholder extension
(67 definitions, including 29 relationships). Counts, complete inventories, review history, named views and
publication differences derive from the same records. Curated JSON Schema excerpts
are cross-checked for field names, requiredness and supported set semantics.
RDF/SHACL/LinkML excerpts use the same IDs and fields; they are selected projections,
not a closed deployment package or output from an implemented exporter.

Regression expectations protect qualified classification, the document-type and
dataset-role distinctions, qualified log retention, unchanged prior publications,
pending proposals, field/condition evidence and UNKNOWN manual criteria. The
original 84 cell identities are retained; added worked inspections and supporting
notes have explicit stable IDs. The ledger keeps every SDK issue planned.

## First-time developer review and Apollo benchmark

The teaching pass added an early consumer destination, an object/lifecycle glossary,
four staged C2 operations, ten explanatory checkpoints and three independent completion
tasks. The completion appears before the optional advanced material. No SDK signatures
were changed. [BENCHMARK.md](BENCHMARK.md) records the inspected Apollo lessons, the
adapted teaching patterns and the remaining gaps in pacing and practice.

Regression checks now reject the previously stale C9 projection subject, C10 publication
counts/review identity, E7 process path and E8 LinkML subject. They also protect C2's
separate acceptance/publication steps and E9's shared recovery checkpoint and case IDs.
C10 experiment counts are
derived from the same catalogue as its publication diff. Selected bundle properties are
checked against all published definition revisions and review targets/reasons.

The logging relevance condition is a published descriptive rule with evidence, not only
an optional-field display annotation. C8 adds the previously missing relationship after
repairing its endpoint; the advisory manual check remains UNKNOWN without a policy change.
Tests protect both distinctions and the consumer's access to the rule.

Read-only choices cannot preview or submit a decision. Action choices retain separate
preview/submission, changed-intent invalidation and repeat-safe behavior. A visual test
found that switching from inspection to retry retained the previous option's reason;
the callback now supplies the newly selected action's reason, with a dedicated regression.
Keyboard selection in VS Code verified the corrected transition after reloading the kernel.
Experiment defaults now explain concrete developer motivations; simulation boundaries remain
in the separate explanation. The live notebook was closed before regenerating portable outputs,
because VS Code's Run All saves widget comm IDs that should not be distributed.

Moving the completion cell exposed Jupytext assigning a fresh native ID; validation
rejected it. Its stable `tour_id` was restored as the native ID before the successful
full run. Pairing and cell identity checks remain mandatory after synchronization.

Saved discovery and mapping results were visually inspected in VS Code after
regeneration. The pinned DPV AI Act resource was also checked for its retained
provisional-agreement scope note; the ontology step now exposes that source-quality
question. MIREOT output correctly reports no semantic-preservation guarantee.

## C6–C7 pacing and feedback pass

C6 now separates preserving distinct meanings, resolving a source occurrence and
comparing a local meaning with a reference. C7 builds one draft across smaller steps
before an explicit plan, impact preview and decision submission. Nine intermediate
views select definitions or fields from the shared catalogue and label their current
state. All 119 preceding cell identities were retained; the new cells have stable IDs.

Five two-part tasks cover proposal review, mapping direction, conditional fields,
key repair and consumer lookup names. Every task has hints, an explicit answer check,
specific incorrect-answer feedback, a worked answer and reset. Checks are authored
teaching feedback, not SDK validation or review decisions. The saved notebook and
HTML retain the questions and expandable worked answers without a widget kernel.

The additional tests check all five correct paths, unanswered and incorrect inputs,
escaped text, feedback invalidation, repeated clicks, rerun preservation, reset and
isolation from model state. Fixture checks reject unknown fields or evidence and
lookup answers that drift from the published contract. Pairing/coverage checks require
all stages and exercises to appear in their assigned chapter. A pacing regression
limits C6–C7 planned blocks to 24 nonblank lines and protects separate preview/submission.

VS Code initially retained the prior helper module in its existing kernel. Restart
again encountered the recorded session-idle issue; Reload Window, followed by Run All
after the kernel became available, executed every cell without errors. Both the
conditional-field and lookup widgets then displayed successful feedback. The notebook
was closed before the final offline regeneration to remove live widget state.
Automated checks cover all five tasks; this manual pass sampled two of them.

The first-time-developer reassessment in [BENCHMARK.md](BENCHMARK.md) now rates the
teaching preview 9.2/10 against the same 9.4/10 Apollo benchmark. These are editorial
judgements; independent learner completion and the time estimate remain unmeasured.


## Discovery instruction lesson

The C4 addition shows default discovery, recruitment-focused additional instructions
and an independent documentation-focused override over the same full source revisions.
Fixture checks protect precedence, fixed response-schema identity, known proposal/source
references and the original schema-failure/recovery example. Planned calls use the new
keyword-only controls; resume retains its existing signature. The fixture text agrees
with the disabled planned instructions. No discovery implementation or new exception
was added to the SDK, and no existing retry or recovery rule was replaced.

All 51 cells completed in VS Code in the existing dark theme after refreshing its
kernel connection. The new prompt capture table and static practice rendered correctly.
The C4 controls showed answer-specific feedback for incorrect precedence/schema choices,
then accepted the corrected choices; dropdown keyboard selection and reset were exercised.
Existing automated widget tests cover correct paths, hints, answer invalidation, reset
and isolated state for all six practices. Light-theme and screen-reader behavior were
not independently re-audited in this pass; the existing standard controls/styles are reused.
Saved notebook and HTML outputs were rebuilt after closing the live editor, retaining
portable static alternatives instead of stale widget state.
