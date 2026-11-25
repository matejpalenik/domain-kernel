# AI in recruitment walkthrough

[Open the interactive notebook](domain-kernel-tour.ipynb)

For host integration and replay guarantees, see the [host integration contract](../../docs/architecture/host-integration.md).

Parse the full English AI Act, review source-cited discovery proposals, and
open the complete published model from the bundle you hand to another developer.

Run the notebook in a local kernel with your own provider key. The first run uses
paid inference. The outputs currently embedded in the notebook are simulated:
they came from a synthetic PDF and scripted provider replies, not a live run.
See the [discovery chapter](../../docs/architecture/discovery-and-reconciliation.md) for more on setup and recovery.

## Run from a checkout

From the repository root:

```sh
uv sync --locked --group notebook --extra documents --extra inference --extra discovery-workflow
```

Open the repository folder in VS Code with the Python and Jupyter extensions. Open
`examples/notebooks/domain-kernel-tour.ipynb`, select the project interpreter
`.venv/bin/python` (`.venv/Scripts/python.exe` on Windows), and choose **Run All**.
Put `OPENAI_API_KEY` in the Git-ignored repository-root `.env` before the first run.
The first run needs an internet connection. It downloads the pinned publisher
PDF, parses all 144 pages with Docling, and retains the text in SQLite.
The SDK runs whole-question discovery with `openai/gpt-6-luna` as the configured
provider. Inspect the draft and its citations before the sample reviewer selects
a documentation handoff for publication. The workspace ledger records provider usage.

To use JupyterLab instead, launch it from the repository root:

```sh
uv sync --locked --group notebook --group notebook-frontend --extra documents --extra inference --extra discovery-workflow
PYTHONPATH="$PWD" uv run --locked --no-sync jupyter lab
```

Open the same notebook from JupyterLab's file browser. Using `jupyter notebook` with
the same options starts Notebook 7.

The notebook stores the verified PDF, SQLite database, and delivered files under
`local/notebook-tour/recruitment-v23/`. Restart the kernel after changing
the checkout or environment. Run All with the same workspace name to reopen
the saved discovery and publication without another provider call.
Choose a new name in `select_demo_workspace` for a fresh run. Paths are
relative to the kernel's working directory. If the English Act pin is invalid,
move the incorrect cached PDF aside and rerun the download cell. The publisher
hashes are in [the acquisition manifest](fixtures/acquisition.json).

## Run from a release archive

Download the wheel and `domain-kernel-tour-<version>.zip` from the same release and
check both against `SHA256SUMS`. Extract the ZIP, then run these commands inside it:

```sh
uv sync --locked --no-install-project --no-default-groups --group notebook --extra documents --extra inference --extra discovery-workflow
uv pip install --python .venv/bin/python --no-deps /absolute/path/to/domain_kernel-0.1.0-py3-none-any.whl
```

Place `OPENAI_API_KEY` in the extracted root's `.env` and select its interpreter. In an extracted archive,
start JupyterLab as above after including `--group notebook-frontend` in the
initial sync. For VS Code, set **Jupyter: Notebook File Root** to `${workspaceFolder}`.
Use `uv run --locked --no-sync` when running a recipe from a prepared archive.

## Recipes

| If you need to… | Start here |
|---|---|
| Parse the original AI Act PDFs or an ELI workbook | [Legislative originals](#legislative-originals), [Docling](#document-parser-resources), [tabular sources](#tabular-resources) |
| Evaluate an OpenAI-compatible gateway against the pinned corpus | [Live discovery with LiteLLM](#live-discovery) |
| Reuse definitions or load an ontology | [Reference packs and dependencies](#reference-packs-and-dependencies), [ontology resources](#ontology-resources) |
| Classify a reviewed ontology or extract a STAR module | [Formal reasoning](#optional-formal-reasoning), [locality extraction](#optional-locality-module-extraction) |
| Share a model with ERP, FDE or GraphRAG | [Manufacturing and independent hosts](#manufacturing-and-independent-hosts) |
| Run on another backend or verify recovery | [PostgreSQL](#postgresql), [S3 and SharePoint](#s3-and-sharepoint), [restart verification](#verify-the-walkthrough) |

### Reference packs and dependencies

Run focused examples through the SDK's integration suite. The tests create
disposable workspaces, compose and reload packs, and review an upgrade against two
exact published versions. Run them from a checkout:

```sh
uv run --locked pytest \
  tests/integration/reference_packs/test_reference_catalog.py \
  tests/integration/modeling/test_reference_pack_selection.py \
  tests/integration/review/test_reference_pack_change.py \
  tests/integration/modeling/test_published_dependencies.py
```

### Manufacturing and independent hosts

The companion recipe uses PDF page 32 of the Atlas Copco LFx 2.0 instruction book and page 1
of the U.S. Department of Energy compressed-air maintenance tip sheet. The
[publisher manifest](fixtures/manufacturing-acquisition.json) records both editions, pages and
digests. Docling parses the original pages. A labelled replay supplies a deliberately
misclassified product type, which the example reviewer corrects against the publisher citation.
The plant asset key, maintenance statuses and pressure collection bound are application choices.

Prepare the `documents`, `ontology` and `linkml` extras and use the commands below in the
locked checkout or the prepared tour archive. The notebook tooling group supplies the example
ERP host's JSON Schema validator.

```sh
manufacturing_originals="$PWD/local/manufacturing-originals"
manufacturing_delivery="$PWD/local/manufacturing-delivery"
uv run --locked --no-sync python -m examples.notebooks.originals --group manufacturing \
  --directory "$manufacturing_originals" --download
uv run --locked --no-sync python -m examples.manufacturing_quickstart \
  --originals "$manufacturing_originals" --output "$manufacturing_delivery"
uv run --locked --no-sync python -m examples.embedding_acceptance --delivery "$manufacturing_delivery"
```

The FDE host creates a new workspace and reviews a transferred maintenance-record shape. The
ERP host validates an asset against the delivered schema and inspects the compound key obligation.
RDF preflight reports the structured set equality limit. An explicitly reviewed derivation
scopes the GraphRAG contract to asset identities and relationships, retaining its exact baseline
pin. GraphRAG validates its own sample asset against that release's instance shapes. The primary
manufacturing bundles retain the exact previous and corrected pressure bounds.

### Legislative originals

Provision the originals from the publishers before running a parser or gateway recipe. The helper
writes an absent file only after verifying its byte length and SHA-256 against the checked-in
[acquisition manifest](fixtures/acquisition.json). It also checks existing files and rejects a
missing or substituted edition. The original PDFs are provisioned separately from the repository.

```sh
export DOMAIN_KERNEL_TOUR_ORIGINALS="$HOME/.cache/domain-kernel-tour/originals"
uv run --locked --group notebook python -m examples.notebooks.originals \
  --directory "$DOMAIN_KERNEL_TOUR_ORIGINALS" --download
```

Omit `--download` to verify an existing tree offline. Use this directory for the
Docling or live discovery recipes below. The notebook downloads the pinned
English Act into its own workspace.

### Ontology resources

Provision the ELI, SKOS and DPV inputs from the
[ontology acquisition manifest](fixtures/ontology-acquisition.json).

```sh
export DOMAIN_KERNEL_TOUR_ONTOLOGIES="$PWD/local/tour-originals"
uv run --locked --group notebook --extra ontology python -m examples.notebooks.originals \
  --group ontologies --directory "$DOMAIN_KERNEL_TOUR_ONTOLOGIES" --download
uv run --locked --extra ontology pytest tests/integration/modeling/interchange/test_ontology_loading.py tests/integration/modeling/test_formal_adoption.py
```

The `lomo` acquisition group provides the LOMO ontology, its import closure and its
companion instance shapes for specialist formal work.

### Document parser resources

To parse original sources, set `DOMAIN_KERNEL_TOUR_ORIGINALS` as above and install the documents
extra. The English Act and Commission guidance use the native PDF pipeline. The WEC PDF needs
OCR on its selected page.

```sh
export DOMAIN_KERNEL_TOUR_DOCLING_MODELS="$HOME/.cache/domain-kernel-tour/docling-models"
uv run --locked --extra documents docling-tools models download layout tableformer rapidocr \
  --rapidocr-backend-lang torch:en --output-dir "$DOMAIN_KERNEL_TOUR_DOCLING_MODELS"
```

The SDK fingerprints the supplied model files and records that digest alongside the original
file revision and Docling engine versions. Parse the selected pages and resolve their citations:

```sh
uv run --locked --group notebook --extra documents python -m examples.notebooks.inspect_originals \
  --originals "$DOMAIN_KERNEL_TOUR_ORIGINALS" --models "$DOMAIN_KERNEL_TOUR_DOCLING_MODELS"
```

### Live discovery

The notebook passes the whole AI Act revision to live discovery. The smaller smoke check
submits one verified AI Act page through the standalone proposal extraction API. It uses the optional
LiteLLM SDK with `openai/gpt-6-luna` and reasoning effort `none`.

Put `OPENAI_API_KEY` in the Git-ignored repository-root `.env`. The runner reads that variable
explicitly and passes it only to the official OpenAI endpoint. It writes the outcome and
reported usage to `local/discovery-luna-smoke.json`.

```sh
uv run --locked --extra inference --extra documents python -m examples.notebooks.live_discovery \
  --originals "$DOMAIN_KERNEL_TOUR_ORIGINALS"
```

The integrated runner uses v23 to discover from the pinned English AI Act and
Commission guidance. It checks lookup names and citation pages and reopens reviewed
releases when the required meanings are available. Private receipts are saved in
`local/v23-live-discovery-integrated/`.

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

### PostgreSQL

The standalone PostgreSQL recipe reviews and publishes the same recruitment system shape in SQLite and PostgreSQL, then
reopens both with independent clients and retries the exact publication intent. PostgreSQL
uses SQLAlchemy's async Psycopg dialect from the optional `postgres` extra.

Set `DOMAIN_KERNEL_TOUR_POSTGRES_DSN` to a PostgreSQL connection URI for a disposable database.
Choose a dedicated namespace with `DOMAIN_KERNEL_TOUR_POSTGRES_SCHEMA`, which defaults to
`domain_kernel_tour`. An operator must initialize it before the kernel opens a workspace.

```sh
uv sync --locked --group notebook --extra ontology --extra linkml --extra documents \
  --extra s3 --extra sharepoint --extra postgres
uv run --locked --no-sync python -m examples.notebooks.postgres_tour --verify
```

The SDK selects the named schema through
`PostgreSQL(dsn=Env(env="DOMAIN_KERNEL_TOUR_POSTGRES_DSN"), schema_name="domain_kernel_tour")`.
The [operator’s SQLAlchemy resource](../../src/domain_kernel/_database.py) can also borrow a
caller-owned async Psycopg engine through `PostgreSQLUnitOfWorkFactory(settings=..., engine=...)`
and `ClientIntegrations(transactions=...)`. Each operation closes its own session and returns
the connection to the caller's pool. Database errors include a recovery action and keep the
connection URI private.

To run the dual-backend tests, set `DK_TEST_POSTGRES_DSN` to a disposable PostgreSQL connection
URI and run `pnpm test:integration`. The fixtures use an isolated temporary schema per scenario.
The required Notebook preview check uses a pinned PostgreSQL 18.6 instance.

### Optional formal reasoning

The reasoning example uses the original ROBOT 1.9.11 distribution with HermiT 1.4.5.456 and OWLAPI 4.5.29.
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

The engine conformance suite compares a named-class specialization with the full pinned DPV AI Act vocabulary.
The focused question proves a transitive subclass entailment using the reviewed link and its
exact external class. The larger vocabulary exceeds the example adapter's fragment and reports
unsupported. Inference results are separate evidence and the reviewed assertions remain exact.
Configure `ReasoningModelValidator` explicitly when consistency, or consistency and satisfiability
of all named classes, must be established before preparation.

Run the engine examples from a checkout:

```sh
uv run --locked --group notebook --extra ontology pytest tests/integration/modeling/interchange/test_ontology_reasoning.py tests/integration/modeling/interchange/test_ontology_modules.py
```

### Optional locality module extraction

With the same pinned setup, the example adapter uses OWLAPI's syntactic STAR algorithm to extract a standalone
RDF/XML ontology from the reviewed recruitment hierarchy. The example adapter advertises OWL 2 DL
under OWL Direct semantics for the documented named-class fragment and for named-class seeds.
The result records the source closure digest, exact seeds, method, regime, limits, driver and
derived ontology identity. Its guarantee applies to entailments over the seed signature.

The conformance suite verifies the same subclass entailment in the reviewed scope and the extracted module.
Provider results that retain whole-source ontology imports explicitly identify those imports and
carry no standalone entailment guarantee. The engine conformance tests include an unrelated
hierarchy and verify that STAR removes it.

### Tabular resources

To profile the checked CSV derivative and resolve the original workbook cells through Docling, provision the exact ELI workbook from the acquisition manifest.

```sh
export DOMAIN_KERNEL_TOUR_TABULAR="$DOMAIN_KERNEL_TOUR_ORIGINALS"
uv run --locked --group notebook --extra documents python -m examples.notebooks.originals \
  --group tabular --directory "$DOMAIN_KERNEL_TOUR_TABULAR" --download
```

Use the provisioning command without `--download` to verify a file you already have.
Run `uv run --locked --extra documents pytest tests/integration/sources/test_tabular_sources.py`.

### S3 and SharePoint

The [adapter tests](../../tests/integration/sources/infrastructure/test_remote_adapters.py) run the installed adapters
with mocked AWS and Graph responses. Run the credentialed recipe with your own configured scope.

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

## Verify the walkthrough

The [ledger](coverage.json) records expected outputs, source pins, and test or recipe
locations for all v1 capability IDs. See [Walkthrough acceptance](VALIDATION.md) for the
verified results and newcomer session. The [source manifest](fixtures/sources.json) labels
the source editions and locators. The acquisition manifest pins the publisher files.

```sh
uv run --locked --group notebook jupytext --sync examples/notebooks/domain-kernel-tour.ipynb
uv run --locked --group notebook --extra documents --extra inference --extra discovery-workflow python -m examples.notebooks._preview.validation --write-outputs --verify-resume
pnpm test:notebook
```

Synchronize after editing either paired file. Keep the cell's ID and `tour_id`
when revising an existing step. Validation with no flags checks the current pair
and ledger without writing. `--write-outputs` executes the live notebook and
updates only its `.ipynb` outputs. Use it only when intentionally refreshing
those outputs, and update the source-mode label to match what ran. With
`--verify-resume`, a restarted kernel blocks external connections, confirms
identical provider usage, and reopens the bundle in a separate consumer. The
notebook tests supply their own PDFs and inference responses in a temporary workspace.
