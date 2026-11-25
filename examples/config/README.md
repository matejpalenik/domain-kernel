# Configuration-driven SDK examples

Use these recipes to configure the SDK in TOML or Python. For the public types and
signatures, see the [SDK reference](https://matejpalenik.github.io/domain-kernel/reference/).

## Client and project selection

Load the configuration once, then open existing projects by name:

```python
from domain_kernel import Client, ClientConfiguration

configuration = ClientConfiguration.from_toml(path="domain-kernel.toml")
client = Client(config=configuration)
project = await client.get_project(name="pump-co")
other_project = await client.get_project(name="another-client")
```

Without a gateway, `Client(config="domain-kernel.toml")` is equivalent. To use a
host-owned inference gateway, pass `model_gateway=gateway` to `from_toml()` or
`ClientConfiguration(...)`, not to `Client` or the TOML file. Constructing the
client does not run inference. The same setup works in a backend or Jupyter.

The embedding application controls which projects a caller can access. Project
selection scopes SDK operations; it is not an authentication mechanism.

`get_project()` does not create a project. Use `await client.create_project(actor=actor, name="pump-co")`
to create one explicitly, or `await client.list_projects()` to list projects.
Two handles can coexist without changing each other's scope. Adapters manage
SDK-owned resources within each operation; the host retains ownership of its
injected pools, transports, and gateways.

## Typed configuration in Python

Use typed records to describe the same settings as a TOML file. The following
example matches [domain-kernel.env.toml](domain-kernel.env.toml) when run from the
repository root. In an application, set `base_dir` to its configuration directory.
The `cfg` namespace contains typed Pydantic configuration records, not live adapter
clients. Pydantic Settings supplies the controlled loading boundary described below.

```python
from pathlib import Path

from domain_kernel import Client, ClientConfiguration
from domain_kernel import configuration as cfg

configuration = ClientConfiguration(
    base_dir=(Path() / "examples/config").resolve(),
    env_file=".env",
    database=cfg.SQLite(path=".domain-kernel/state.sqlite3"),
    readers=[
        cfg.S3Reader(
            name="inputs",
            bucket="client-inputs-example",
            prefix="manufacturing/",
            region="eu-central-1",
            credentials=cfg.AwsProfile(profile="client-inputs"),
        ),
        cfg.SharePointReader(
            name="manuals",
            drive_id="replace-with-drive-id",
            root_item_id="replace-with-folder-item-id",
            credentials=cfg.EntraClientSecret(
                tenant_id=cfg.Env(env="DK_SHAREPOINT_TENANT_ID"),
                client_id=cfg.Env(env="DK_SHAREPOINT_CLIENT_ID"),
                client_secret=cfg.Env(env="DK_SHAREPOINT_CLIENT_SECRET"),
            ),
        ),
    ],
    parsers=cfg.Parsers(documents=cfg.DoclingParser()),
    storage=cfg.Storage(
        artifact_store=cfg.S3Store(
            name="artifacts",
            bucket="domain-kernel-outputs-example",
            prefix="artifacts/",
            region="eu-central-1",
            credentials=cfg.AwsProfile(profile="domain-kernel-outputs"),
        ),
    ),
    processing=cfg.InMemoryProcessing(
        max_source_bytes=64 * 1024 * 1024,
        max_concurrent_sources=2,
    ),
    retention=cfg.Retention(
        originals=False,
        extracted_text=False,
        evidence_excerpts=False,
    ),
)

client = Client(config=configuration)
project = await client.get_project(name="pump-co")
```

`ClientConfiguration` covers metadata persistence, readers, parsers, stores,
credential providers, processing, and retention. The injected `gateway` retains
its own inference-provider, model, and authentication configuration.

Constructing the configuration records performs structural validation without
reading dotenv files, resolving credentials, or contacting services. Constructing
the Client loads the selected configuration input, resolves references, and
performs final validation. Authentication and connectivity are checked when an
operation uses a capability. Neither step creates projects, provisions storage,
or runs inference.

## Pydantic Settings and fail-closed validation

Pydantic validates the public configuration records. Pydantic Settings loads
resolved runtime settings from the explicitly selected sources. Defaults apply
only to omitted values. Unknown fields, unknown adapter types, invalid limits,
and incompatible credential or store bindings fail rather than falling back.

Invalid direct record construction raises `ValidationError`. Invalid file input
or unresolved settings raise `ConfigurationError`. `client.inspect_configuration()`
reports the captured configuration without exposing resolved secrets or performing
I/O. Neither construction nor inspection creates projects, provisions storage,
or verifies remote permissions. Those checks belong to operations that use the
configured resources.

## TOML and dotenv files

The SDK loads `.env` only when explicitly configured. It does not expand
`${VARIABLE}` in TOML. Use explicit references so secret values stay out of TOML:

```toml
schema_version = 1
env_file = ".env"

[credentials.sharepoint]
provider = "entra_client_secret"
tenant_id = { env = "DK_SHAREPOINT_TENANT_ID" }
client_id = { env = "DK_SHAREPOINT_CLIENT_ID" }
client_secret = { env = "DK_SHAREPOINT_CLIENT_SECRET" }
```

The corresponding development-only `.env` file is:

```dotenv
DK_SHAREPOINT_TENANT_ID=replace-with-tenant-id
DK_SHAREPOINT_CLIENT_ID=replace-with-application-id
DK_SHAREPOINT_CLIENT_SECRET=replace-with-client-secret
```

Copy [.env.example](.env.example) to `.env` beside the selected TOML file and
replace the placeholders. The actual `.env` file is ignored by Git; the template
contains no real credentials. The complete dotenv-enabled configuration is
[domain-kernel.env.toml](domain-kernel.env.toml).

The resolution rules are:

1. Select a TOML file or a ClientConfiguration instance. Do not implicitly merge
   the two. Explicit settings take precedence over SDK defaults.
2. Load only the explicitly selected `env_file`. Do not search parent directories
   or mutate `os.environ`. An explicitly configured missing file is an error.
3. For a `cfg.Env(env="NAME")` or `{ env = "NAME" }` reference, prefer the process
   environment over the dotenv value. This lookup is the only way environment
   values affect these configuration fields.
4. Ignore unrelated dotenv entries. Missing, valueless, or empty required values
   fail validation with the variable name and configuration field, never the
   secret value. Keep dotenv values literal; do not interpolate variables or
   execute shell expressions.
5. Capture the resolved reference values per Client. Reinitialization is required
   to adopt configuration or dotenv changes. Refreshable cloud credentials can
   still renew their issued tokens through their selected provider.

For TOML input, resolve paths and `env_file` relative to that file. For Python
input, use `base_dir`, defaulting to the working directory captured when the
configuration is constructed. This keeps paths stable when notebook cells later
change directories. Each Client has its own dotenv overlay; loading a second
client must not alter the first client's configuration or the process environment.

In production, omit `env_file` and provide referenced values through the deployment
environment or select an approved credential provider. The public configuration
retains references, not resolved secrets. Redact resolved values in all diagnostic
and serialization paths.

## Configuration choices

| Example | Project state | Input reader | Artifact store | Credentials |
| --- | --- | --- | --- | --- |
| [Local](domain-kernel.local.toml) | Embedded SQLite | Local directory | Local directory | None |
| [S3](domain-kernel.s3.toml) | Embedded SQLite | S3 | S3 | Separate AWS profiles |
| [PostgreSQL and S3](domain-kernel.postgres-s3.toml) | PostgreSQL | S3 | S3 | Database DSN environment reference and AWS credential chain |
| [Python/TOML with dotenv](domain-kernel.env.toml) | Embedded SQLite | S3 and SharePoint | S3 | Separate AWS profiles and client-scoped SharePoint environment references |

Pass the selected file directly as `config=...`; the examples are complete
alternatives, not implicitly merged layers. Omitting `[database]` selects embedded
SQLite at `.domain-kernel/state.sqlite3`. Omitting artifact-store configuration
selects the local `.domain-kernel/artifacts` store. Paths inside the file resolve
relative to its directory, independent of the notebook's working directory.

For a minimal local deployment, the defaults make this file sufficient:

```toml
schema_version = 1
```

The local reader defaults to the configuration directory. The longer local
example narrows it to `./data` and explicitly selects optional parsers. Named
reader paths must stay within their configured root or prefix. Parser options
such as sheets or pages remain available on typed source descriptors.

`parsers` select format adapters; `readers` locate inputs; `stores` select output
destinations. Selecting a PostgreSQL state backend does not move documents or
change their readers. Selecting S3 does not require PostgreSQL. Install the
`postgres`, `s3`, `sharepoint`, and `documents` extras for the capabilities you use.

To serve a reference-pack catalog from a separate approved directory, add a named
filesystem reader to your selected TOML file and bind the catalog to it:

```toml
[readers.references]
type = "filesystem"
root = "./reference-packs"

[reference_packs]
reader = "references"
```

Keep an existing `inputs` reader when adding this entry. Without a configured
catalog, listing packs returns an empty page; looking up a missing pack does not
trigger a public download.

AWS profiles and role-based credentials follow the
[AWS SDK's credential mechanisms](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).
`aws_default_chain` explicitly enables that provider's chain for the named
capability. A resolved credential is not stored in a source descriptor, evidence
record, or project object. Separate reader and store credentials allow different
input and output accounts; actual permissions come from the configured providers.

The native AWS credential chain uses the AWS SDK's standard process environment,
profile, and runtime-identity sources. A client-local dotenv overlay does not
automatically populate those sources. To deliberately use AWS keys from that
overlay, select an explicit static provider:

```toml
[credentials.input_aws]
provider = "aws_static"
access_key_id = { env = "DK_AWS_ACCESS_KEY_ID" }
secret_access_key = { env = "DK_AWS_SECRET_ACCESS_KEY" }
# Include this field when using temporary credentials supplied as a triple.
session_token = { env = "DK_AWS_SESSION_TOKEN" }
```

The matching Python record is `cfg.AwsStatic` with `cfg.Env(env=...)` references.
Omit `session_token` when it does not apply. This provider does not refresh a
manually supplied credential triple. Prefer refreshable profiles or workload
identity providers when available. For SharePoint, the configured Entra client
credential obtains and refreshes access tokens; do not store bearer tokens in the
configuration. Actual Microsoft Graph permissions depend on the requested API.

For PostgreSQL, supply `DK_DATABASE_DSN` through the environment or deployment
secret tooling. It holds a
[PostgreSQL connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
including the required authentication and TLS settings. The file contains only
the reference `dsn = { env = "DK_DATABASE_DSN" }`. To use a local dotenv file with
this example, add `env_file = ".env"` before its first table. Validate a required
reference without printing its value, and redact resolved secrets from all
diagnostic output.

Other databases and secret providers can implement typed adapter contracts.
Unsupported types must fail clearly. Switching a database configuration selects a
different state backend; transferring existing projects requires an explicit
migration. Loading configuration must not provision a database, create buckets,
or create projects. Backend schemas must be prepared through explicit operations.

## Notebook discovery example

Select the existing project and model. Ingest each document through the
configured reader, then discover from the exact revisions:

```python
from domain_kernel import Client, ClientConfiguration, Excel, PDF, ReaderLocation

config = ClientConfiguration.from_toml(path="domain-kernel.toml", model_gateway=gateway)
client = Client(config=config)
project = await client.get_project(name="pump-co")
model = await project.get_model(name="manufacturing")
actor = "user:model-editor"

components = await project.ingest_source(
    actor=actor,
    name="components",
    source=Excel(location=ReaderLocation(reader="inputs", path="components.xlsx")),
)
manual = await project.ingest_source(
    actor=actor,
    name="production-manual",
    source=PDF(location=ReaderLocation(reader="inputs", path="production_manual.pdf")),
)
run = await model.discover(
    actor=actor,
    sources=[components.revision, manual.revision],
)
cases = [case async for case in model.iter_review_cases(run_id=run.id)]
```

With the local example, these paths refer to files below `./data`. With either S3
example, they refer to objects below `manufacturing/` in the configured input
bucket. The source descriptors remain unchanged. Resolve the configured provider
and record its actual origin, version, and content digest when acquiring content.
Configure a supported gateway, such as `LiteLLMGateway`, with your provider and
model. No workflow or gateway opt-in is needed. See the
[document discovery guide](../../docs/document-discovery.md) for setup and resume.

With the dotenv-enabled example, select `ReaderLocation(reader="manuals", path=...)`
for a file under the configured SharePoint folder. Choosing a reader selects its
configured credentials and scope; it does not change the source format descriptor.

The discovery result remains inspectable while review is pending. After review
and publication, [export the exact published bundle](../../ARCHITECTURE.md#export-a-published-model)
to a configured store.

The store resolves its destination and credentials from configuration. Artifact
keys are scoped to the persistent project identity, so two projects do not
overwrite each other's exports. Existing immutable versions must not be replaced
silently. Successfully publishing a local model and successfully exporting its
bundle are separate outcomes; export must report storage failures accurately.

## Processing and retention

The examples select in-memory source processing and disable persistence of
originals, extracted text, and evidence excerpts. These are explicit example
policies; they do not establish defaults for every sensitive derivative. Project
state, structural metadata, source references, decisions, and published models
still persist in the configured database or artifact store under their policies.
Reopening evidence may require access to the exact provider version and content
digest originally consumed.

Configuring a writable store does not authorize copying originals. Original
retention or a later source-revision copy must be explicitly requested and target
an approved configured store. See [retention policies](../../ARCHITECTURE.md#retention-policies)
and [resource limits](../../ARCHITECTURE.md#resource-limits-and-data-security)
for replay, processing bounds, and the no-spill guarantee.
