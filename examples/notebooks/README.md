# Domain Kernel Tour

**Live SDK review, publication and bundle reload.** One notebook follows a developer
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
   uv sync --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents --extra s3 --extra sharepoint
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
processing-duration quantity. The real SDK creates the workspace, records review and
publishes both revisions. C3 uses the separately provisioned original PDF for verified acquisition.

The manual tour uses `local/notebook-tour/recruitment-manual`. Preserve the name to
resume review and publication after a kernel restart. Choose an unused demo name in
C1 for a fresh sample. That changes the selected workspace without deleting prior
releases. The portable handoff writes temporary copies and cleans them up after the
consumer exits.

For a headless run using the same application fields and bilingual provider labels:

```sh
uv run --locked --no-dev python -m examples.recruitment_quickstart
```

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
source support, inferred structure and application-authored choices. This edition is a teaching baseline. Verify the legal edition relevant to your own model.
C5 loads the pinned ELI and DPV distributions. E1 can also load the versioned
LOMO ontology and its import closure, with its companion instance shapes inspected separately.
C1 creates the SQLite workspace, C2 reviews the connected graph, and E9 reopens
the workspace from a new client. C7, E6 and R1 review the application shapes, and C8 and R1 validate exact compiled
candidates. C2 and C8 publish immutable releases. C2 and C9 transfer their canonical JSON files
to an independent consumer. E7 reviews a descriptive process and decision table and inspects
its portable release. E2 composes and reloads authored reference packs and checks the remapped
unit. E2 also loads the pinned filesystem catalog, reviews a local adaptation and independently
loads its published reference mapping. Labelled previews remain available alongside the SDK cells.

## Original inputs

C3 acquires the exact English Official Journal AI Act, Commission guidance and WEC Europe paper.
C10 adds the French Official Journal edition to the same named legal source. The application can
inspect either immutable digest independently. The notebook reads the originals through the
configured SDK filesystem reader and keeps document parsing as a separate step.

Provision the originals from the publishers before starting the notebook kernel. The helper
writes an absent file only after verifying its byte length and SHA-256 against the checked-in
[acquisition manifest](fixtures/acquisition.json). It also checks existing files and rejects a
missing or substituted edition. The original PDFs are provisioned separately from the repository.

```sh
export DOMAIN_KERNEL_TOUR_ORIGINALS="$HOME/.cache/domain-kernel-tour/originals"
uv run --locked --group notebook python -m examples.notebooks.originals \
  --directory "$DOMAIN_KERNEL_TOUR_ORIGINALS" --download
```

Take `--download` off the command to verify an already provisioned tree without a network
connection. Start the notebook kernel with the same environment variable. If the variable is
absent, the two acquisition cells show the provisioning prompt and subsequent preview chapters
still run. The reading version includes the observed hashes and counts from a provisioned run.

Verify the full notebook journey and reopened SQLite state with the originals present.

```sh
uv run --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents --extra s3 --extra sharepoint python -m examples.notebooks._preview.validation \
  --verify-resume
```

### Ontology resources

C5 reads the ELI, SKOS and DPV inputs pinned in the [ontology acquisition manifest](fixtures/ontology-acquisition.json).
Use the SDK's ontology extra and provision the original bytes before running the notebook.

```sh
export DOMAIN_KERNEL_TOUR_ONTOLOGIES="$DOMAIN_KERNEL_TOUR_ORIGINALS"
uv run --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents python -m examples.notebooks.originals \
  --group ontologies --directory "$DOMAIN_KERNEL_TOUR_ONTOLOGIES" --download
```

Set `DOMAIN_KERNEL_TOUR_LOMO` and provision the `lomo` group the same way to inspect the
LOMO ontology, its complete import closure and the separate instance shapes in E1. Use the
same variables when saving observed notebook outputs.

### Document parser resources

C3 can resolve previously captured passages through the SDK with its default offline inputs. For
the provisioned parser run, set `DOMAIN_KERNEL_TOUR_ORIGINALS` as above and install the documents
extra. The English Act and Commission guidance use the native PDF pipeline. The WEC PDF needs
OCR on its selected page.

```sh
export DOMAIN_KERNEL_TOUR_DOCLING_MODELS="$HOME/.cache/domain-kernel-tour/docling-models"
uv run --locked --extra documents docling-tools models download layout tableformer rapidocr \
  --rapidocr-backend-lang torch:en --output-dir "$DOMAIN_KERNEL_TOUR_DOCLING_MODELS"
```

Provision models before starting the kernel. The SDK fingerprints the supplied model files and
records that digest alongside the original file revision and Docling engine versions. C3 records
the observed page spans in the [ledger](coverage.json).

### Live discovery

The default C4 notebook uses a labelled structured response replay. The opt-in smoke check
submits one verified AI Act page through the same SDK extraction API. It uses the optional
LiteLLM SDK with `openai/gpt-6-luna` and reasoning effort `none`.

Put `OPENAI_API_KEY` in the Git-ignored repository-root `.env`. The runner reads that variable
explicitly and passes it only to the official OpenAI endpoint. It writes the outcome and
reported usage to `local/discovery-luna-smoke.json`.

```sh
uv run --locked --extra inference --extra documents python -m examples.notebooks.live_discovery \
  --originals "$DOMAIN_KERNEL_TOUR_ORIGINALS"
```

The integrated runner uses the same extraction contract for the complete pinned English AI Act
and Commission guidance. It checks lookup names and evidence pages against the frozen corpus
expectations, reviews a scoped update, and independently reloads the two releases when both
review inputs are present. The provider response and release evidence stay under the Git-ignored
`local/live-discovery-integrated/` directory. The [recorded integrated receipt](fixtures/discovery-luna-integrated.json)
reports automatic verification and both release digests. Semantic grading remains part of final acceptance.

```sh
uv run --locked --extra inference --extra documents python -m examples.notebooks.live_journey \
  --originals "$DOMAIN_KERNEL_TOUR_ORIGINALS"
```

The shared campaign ledger reserves at most 1 million input tokens and 100,000 output tokens
across smoke, integrated, and release runs. Each attempt reserves before calling the provider.
Unknown usage stays reserved. Observed usage replaces its reservation after a response. If the
endpoint, schema, key, or budget prevents the run, the receipt marks the live evidence incomplete.

Use `LiteLLMGateway(model=..., api_base=..., api_key=...)` in a host client to configure another
OpenAI-compatible endpoint that supports the structured response contract. Supply that endpoint's
own key.

### Optional formal reasoning

E1 uses the original ROBOT 1.9.11 distribution with HermiT 1.4.5.456 and OWLAPI 4.5.29.
Install a Java 17 or newer JDK. Select its home explicitly with `JAVA_HOME` if the shell uses
a launcher or version-manager shim. From the repository root, provision the pinned sources
and engine before starting the kernel.

```sh
export DOMAIN_KERNEL_TOUR_ONTOLOGIES="$PWD/local/tour-originals"
uv run --locked --group notebook --extra ontology python -m examples.notebooks.originals \
  --directory "$DOMAIN_KERNEL_TOUR_ONTOLOGIES" --group ontologies --download

mkdir -p "$PWD/local/engines"
export DOMAIN_KERNEL_TOUR_ROBOT_JAR="$PWD/local/engines/robot-1.9.11.jar"
curl --fail --location --proto '=https' \
  https://github.com/ontodev/robot/releases/download/v1.9.11/robot.jar \
  -o "$DOMAIN_KERNEL_TOUR_ROBOT_JAR"
```

The host verifies the 82,708,624-byte JAR against
`53cd275c8e4c0dad1fc2c1c34174876795cd7d6b6926e1444adcbb0cb3c7ab26`
and captures the driver digest in the reported engine version. It passes validated named-class
operations from the selected graphs of an exact local closure into a process with a 384 MiB
Java heap. The SDK applies the requested time and input/output limits. The host reaps the
process on cancellation. Import inputs come exclusively from the verified local closure.

| Profile and semantics | Supported tasks and input |
| --- | --- |
| OWL 2 DL under OWL Direct semantics | Consistency, named-class classification, and entailment of a supplied query with logical axioms. Supported asserted axioms are named subclass, equivalence, disjointness, and named-individual class assertions with declared terms. |
| Other profile, semantics or RDF feature | Unsupported or incomplete with consistency and entailment left unknown where unestablished. |

E1 compares the reviewed named-class specialization with the full pinned DPV AI Act vocabulary.
The focused question proves a transitive subclass entailment using the reviewed link and its
exact external class. The larger vocabulary exceeds the example adapter's fragment and reports
unsupported. Inference results are separate evidence and the reviewed assertions remain exact.
Configure `ReasoningModelValidator` explicitly when consistency, or consistency and satisfiability
of all named classes, must be established before preparation.

### Tabular resources

E4 profiles the checked CSV derivative with DuckDB. To verify its transformation and resolve the
original cells with Openpyxl, provision the exact ELI workbook from the acquisition manifest.

```sh
export DOMAIN_KERNEL_TOUR_TABULAR="$DOMAIN_KERNEL_TOUR_ORIGINALS"
uv run --locked --group notebook --extra tabular python -m examples.notebooks.originals \
  --group tabular --directory "$DOMAIN_KERNEL_TOUR_TABULAR" --download
```

Keep this variable when you launch the notebook or save the reading outputs. Use the provisioning
command without `--download` to verify a file you already have.

### S3 and SharePoint

E9 runs the installed adapters against mocked AWS and Graph responses. It compares the checked
ELI CSV from both input bindings with the local capture and exports the exact recruitment bundle
through a separate S3 client. Run the credentialed recipe during final acceptance.

1. Place copies of the verified AI Act and supporting public originals in a dedicated S3 input
   prefix and a dedicated SharePoint folder. Keep their names and bytes from the acquisition
   manifest. Reserve a separate S3 prefix for SDK artifacts.
2. Give the S3 input role `s3:ListBucket` scoped to that prefix and read access to its objects.
   Enable versioning and grant `s3:GetObjectVersion` to test historical reads. The output role
   needs conditional `s3:PutObject` and exact reads in its own prefix for verification and recovery.
   [S3 listing](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html) · [S3 versions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html) · [Conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
3. Configure a tenant-specific Entra application and a reviewed Graph grant for the approved
   drive. Record its drive ID and folder item ID. Put the tenant, application ID and secret in
   the host environment under the names below. An explicitly selected Git-ignored `env_file`
   also works. [Entra client credentials](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow) · [Graph folder scope](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0) · [Version downloads](https://learn.microsoft.com/en-us/graph/api/driveitemversion-get-contents?view=graph-rest-1.0)

```python
from domain_kernel import Client, ClientConfiguration, ClientIntegrations, DoclingParser
from domain_kernel.configuration import (
    AwsProfile,
    EntraClientSecret,
    Env,
    S3Reader,
    S3Store,
    SharePointReader,
    Storage,
)

cloud = Client(
    config=ClientConfiguration(
        base_dir=demo_workspace,
        readers=[
            S3Reader(
                name="aws-inputs",
                bucket="approved-inputs",
                prefix="recruitment-demo/",
                region="eu-central-1",
                credentials=AwsProfile(profile="recruitment-inputs"),
            ),
            SharePointReader(
                name="graph-inputs",
                drive_id=approved_drive_id,
                root_item_id=approved_folder_id,
                credentials=EntraClientSecret(
                    tenant_id=Env(env="DK_GRAPH_TENANT_ID"),
                    client_id=Env(env="DK_GRAPH_CLIENT_ID"),
                    client_secret=Env(env="DK_GRAPH_CLIENT_SECRET"),
                ),
            ),
        ],
        storage=Storage(
            artifact_store=S3Store(
                name="cloud-artifacts",
                bucket="approved-outputs",
                prefix="recruitment-demo/",
                region="eu-central-1",
                credentials=AwsProfile(profile="recruitment-outputs"),
            ),
        ),
    ),
    integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser()}),
)
```

Use the same named workspace when reopening the recruitment publication for export. Use `PDF`
with a `ReaderLocation` and the manifest's `expected_hash` to inspect a single file from each
backend. Use `SourceFolder` with `recursive=True` for the approved folder. Compare the revision
digests with the local acquisition and inspect each recorded provider version and any per-source
failure. Export the exact saved release to `cloud-artifacts`, then repeat with the same export
idempotency key to verify recovery. Remotely stored originals and exports have a 64 MiB limit.
Clean up only the objects and version history created for this dedicated demo.

## Edit, synchronize and verify

Edit either paired file, not both independently. Preserve native cell IDs and the
matching `tour_id` metadata. Synchronize explicitly from the repository root:

```sh
uv run --locked --group notebook jupytext --sync examples/notebooks/domain-kernel-tour.ipynb
uv run --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents --extra s3 --extra sharepoint python -m examples.notebooks._preview.validation
uv run --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents --extra s3 --extra sharepoint pytest tests/unit/test_notebook_preview.py tests/unit/test_notebook_practice.py tests/integration/test_notebook_preview.py
```

Validation is read-only. It checks pairing, all 21 sections, all 43 owners, saved SDK output, fixture
pins, complete snapshot references, field/condition evidence, bounded named views,
curated JSON Schema expectations, bundle inventory/review revisions, experiment-to-chapter
consistency, and planned-call syntax/documented keyword
names. The keyword check is a conservative cross-check of the interface guide;
it does not resolve receiver types, validate all argument types or run future SDK
calls. The integration suite executes the tour in a fresh offline kernel with its
own temporary workspace and exercises the preview widget callbacks.

After intentional changes, provision the originals and rebuild the saved outputs and offline
reading artifact.

```sh
uv run --locked --group notebook --extra ontology --extra linkml --extra tabular --extra documents --extra s3 --extra sharepoint python -m examples.notebooks._preview.validation --write-outputs
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
