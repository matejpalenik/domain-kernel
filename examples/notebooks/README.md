# Domain Kernel Tour

**Live SDK scope selection and shape authoring.** One notebook follows a developer
at a lobbying organisation building a reusable domain model for AI-in-recruitment
legislative analysis. The 60–90 minute main journey contains C1–C10, followed by
optional E1–E10 and R1. The downstream analysis application is outside the tour.

Open [the notebook](domain-kernel-tour.ipynb) for experiments, or open
[the saved reading version](domain-kernel-tour.html) in a browser. The reading
version works offline and includes the canonical figures, tables, source ledger and
illustrative exports. Python-backed controls require a running notebook kernel.
Saved files intentionally omit widget comm IDs/state from a previous kernel;
Run All creates fresh controls.

## Start in VS Code

1. Open the **repository folder**, not just this subdirectory.
2. Install the recommended Microsoft Python and Jupyter extensions. Optional:
   Jupytext Sync can synchronize the pair when saving; it is not needed to run it.
3. Provision the locked development environment from the repository root:

   ```sh
   uv sync --locked --group notebook
   ```

4. Open `examples/notebooks/domain-kernel-tour.ipynb`. Use **Select Kernel → Python
   Environments → .venv**. The interpreter is `.venv/bin/python` on macOS/Linux and
   `.venv/Scripts/python.exe` on Windows. No global kernel registration is needed.
5. Choose **Run All**. The committed VS Code setting `jupyter.notebookFileRoot`
   selects `${workspaceFolder}` explicitly. Other frontends must also use the
   repository root as their execution directory.

Use VS Code's **Outline** or **Go to Symbol in Editor** (`Cmd+Shift+O` on macOS,
`Ctrl+Shift+O` on Windows/Linux) to jump to a chapter, exercise or recipe. The
reading version also provides navigation links.

No credentials, source downloads or network requests are needed after provisioning.
Do not run `asyncio.run()` or install nested-event-loop patches in notebook cells;
planned persistence calls use top-level `await`. No cell changes directories or
modifies `sys.path`. If `examples` cannot be imported, check the execution directory
and selected environment rather than adding a path workaround.

In C1, run the scope cell to select the original English AI Act edition from the checked-in
manifest and inspect its SDK `ContentHash` and the model's `ModelKind`. C7 authors the provision
locator, E6 inspects an actor-role assignment with bilingual terminology, and R1 builds a local
processing-duration quantity. The workspace and review steps are labelled previews. The original
PDF is provisioned for the future ingestion step.

Each chapter explains what you have learned and why the next step matters, names
its prerequisites, and offers an isolated experiment. Read-only preview selections
update immediately without a reason or submission. For a sample change, choose an option,
enter a reason, **Preview impact**, then **Apply sample action**. Reset is explicit.
Rerunning cells preserves the branch; restarting the kernel rebuilds the preview.
Selecting or rendering a value never approves changes or fetches evidence.

Start with each chapter's highlighted result; open supporting details when you need
the complete inventory or diagnostics. Model exploration offers both a diagram and
a directed connection matrix. C9 follows one Article 13 requirement from evidence
through review to publication, then inspects what an independent bundle consumer can
reuse. Its field selector is read-only; citations do not automatically load passages
or determine whether a requirement applies.

The opening previews the final consumer contract before you configure a workspace. C2 separates
building, impact inspection, decision submission and publication. Each main chapter ends with a
question and an expandable explanation; the main journey ends with three independent inspection
tasks and a route map for the advanced exercises. [The educational benchmark](BENCHMARK.md)
records the comparison with Apollo Odyssey and the remaining learning-design gaps.

C4 teaches per-run discovery focus over the full AI Act, inspects the captured instructions,
and compares an isolated prompt override with the same SDK output schema. The brief guides
relevance; it is not a hard passage filter or proof of extraction completeness. Existing failure
and recovery behavior is unchanged. C6–C7 use short stages with one current decision or draft
change at a time. Six **Your turn** tasks ask you to check prompt precedence and validation,
review proposals, repair a mapping direction, design a conditional field,
repair a key and find consumer lookup names. **Check your answer** provides specific feedback;
**Hint**, **Show worked answer** and **Reset practice** support retrying. Reading or checking an
answer never submits a review decision. Cell reruns retain your inputs and feedback; changing
an answer invalidates its previous feedback. The saved reading version includes the same tasks
and expandable worked answers without a running kernel.

## Files and source provenance

- `domain-kernel-tour.ipynb` is the canonical notebook, with saved rich outputs.
- `domain-kernel-tour.py` is its Jupytext percent-format source for readable diffs.
- `_preview/` contains bounded, example-only views and experiment controls. It is
  outside the SDK and is neither a replacement client nor a persistence engine.
- `fixtures/sources.json` records editions, locators, attribution and verification.
  `acquisition.json` records sizes and SHA-256 hashes of acquired original assets.
  Originals are not redistributed. The ELI CSV is a labelled three-row derivative.
- `fixtures/catalogue.json` shares definitions, revisions, evidence links, review outcomes
  and named snapshots across all model views. Counts and publication differences are derived.
- `fixtures/scenes.json` contains immutable authored outcomes; `projections.json`
  contains illustrative format excerpts, not verified SDK export bytes.
- `fixtures/learning.json` contains bounded C6–C7 stage selections and C4/C6/C7 practice feedback.
  Stage fields and the consumer lookup answers are checked against the shared catalogue.
- `fixtures/discovery-prompts.json` contains authored default/additional/override captures.
  Fixture versions are not released SDK versions; schema identity and precedence are checked.
- `coverage.json` maps stable cells to every DK issue and records live SDK steps,
  source pins and expected outputs. `VALIDATION.md` records preview checks.

The original 2024 Official Journal AI Act PDFs in English and French were acquired,
hashed and checked for the selected passages. Stable passage IDs retain exact article,
paragraph/annex and PDF-page locators. Field and condition annotations distinguish
source support, inferred structure and application-authored choices. This edition is
a teaching baseline, not a claim about the law currently in force. LOMO documentation
was acquired; its complete ontology/shape dependency closure remains unavailable.
C1 creates the SQLite workspace, C2 reviews the connected graph, and E9 reopens
the workspace from a new client. C7, E6 and R1 review the application shapes.
Parsing, inference, reasoning, publication and projection outputs remain simulated.

## Edit, synchronize and verify

Edit either paired file, not both independently. Preserve native cell IDs and the
matching `tour_id` metadata. Synchronize explicitly from the repository root:

```sh
uv run --locked --group notebook jupytext --sync examples/notebooks/domain-kernel-tour.ipynb
uv run --locked --group notebook python -m examples.notebooks._preview.validation
uv run --locked --group notebook pytest tests/unit/test_notebook_preview.py tests/unit/test_notebook_practice.py tests/integration/test_notebook_preview.py
```

Validation is read-only. It checks pairing, all 21 sections, all 43 owners, saved SDK output, fixture
pins, complete snapshot references, field/condition evidence, bounded named views,
curated JSON Schema expectations, bundle inventory/review revisions, experiment-to-chapter
consistency, and planned-call syntax/documented keyword
names. The keyword check is a conservative cross-check of the interface guide;
it does not resolve receiver types, validate all argument types or run future SDK
calls. The integration suite executes the tour in a fresh offline kernel with its
own temporary workspace and exercises the preview widget callbacks.

After intentional changes, rebuild saved outputs and the offline reading artifact:

```sh
uv run --locked --group notebook python -m examples.notebooks._preview.validation --write-outputs
```

This executes before writing. CI never regenerates the pair or rewrites fixtures.
Review fixture changes before updating their SHA-256 entries in the coverage ledger.
Keep original source hashes separate from hashes of authored fixture files.

## Replace one operation with the real SDK

For each owning roadmap issue, retain the narrative, stable cell identity and visual
structure. Enable its planned call and supply its declared inputs. Connect the actual
result to a presentation view, remove that operation's fixture assignment and add
its real acceptance evidence. Extend the ledger schema/status checks as real work
lands; never mark an SDK issue complete because its preview passes.

Do not add a global real/mock switch or silently fall back to fixtures. During the
transition, label individual simulated operations explicitly. Keep the existing
real-SDK milestone gates, independent consumer checks, live semantic-quality work
and engine/frontend conformance requirements intact.
