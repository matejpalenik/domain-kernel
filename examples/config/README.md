# Configuration-driven SDK examples

These examples describe the requested SDK design. The repository currently
contains the engineering baseline and a greeting entry point; `Client`,
`ClientConfiguration`, the loader, project methods, and adapters below are not
implemented. The requested public entry points are `Client` and
`ClientConfiguration`. Nested configuration helper names and signatures remain
illustrative.

Python examples use explicit keyword arguments.

## Client and project selection

Configure the deployment once, then select the project to work with:

```python
from domain_kernel import Client, ClientConfiguration

client = Client(config="domain-kernel.toml", model_gateway=gateway)

# An in-code configuration uses the same schema; omitted fields use SDK defaults.
client_two = Client(config=ClientConfiguration(), model_gateway=gateway)

project = client.projects.get(key="pump-co")
other_project = client.projects.get(key="another-client")
```

`gateway` is an application-supplied implementation of the model-inference
contract. Creating or inspecting the client must not invoke it. The same
initialization works in a Python backend and a Jupyter notebook.

The client supplies project management, and each project supplies domain work:

| Operation | Proposed call |
| --- | --- |
| Create a project explicitly | `client.projects.create(key="pump-co")` |
| Retrieve an existing project | `client.projects.get(key="pump-co")` |
| List accessible projects | `client.projects.list()` |
| Discover a domain | `await project.discover(sources=[...])` |
| Inspect or ingest sources | `project.sources` |
| Control discovery stages | `project.discovery` |
| Inspect reconciliation | `project.reconciliation` |
| Submit review decisions | `project.review` |
| Validate, approve, publish, and export | `project.modeling` |

The embedding application controls which projects a caller can access. Project
selection scopes SDK operations; it is not an authentication mechanism.

`get()` does not create a project. Two project handles can coexist without
changing each other's scope. Ordinary usage needs no `open()` / `close()` calls:
the adapters acquire and release SDK-owned resources within operations. An
application retains ownership of any pools, transports, or gateways it injects.

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
    credentials={
        "input_aws": cfg.AwsProfile(profile="client-inputs"),
        "output_aws": cfg.AwsProfile(profile="domain-kernel-outputs"),
        "sharepoint": cfg.EntraClientSecret(
            tenant_id=cfg.Env(env="DK_SHAREPOINT_TENANT_ID"),
            client_id=cfg.Env(env="DK_SHAREPOINT_CLIENT_ID"),
            client_secret=cfg.Env(env="DK_SHAREPOINT_CLIENT_SECRET"),
        ),
    },
    readers={
        "inputs": cfg.S3Reader(
            bucket="client-inputs-example",
            prefix="manufacturing/",
            region="eu-central-1",
            credentials="input_aws",
        ),
        "manuals": cfg.SharePointReader(
            drive_id="replace-with-drive-id",
            root_item_id="replace-with-folder-item-id",
            credentials="sharepoint",
        ),
    },
    parsers={
        "excel": cfg.OpenpyxlParser(),
        "documents": cfg.DoclingParser(),
    },
    stores={
        "artifacts": cfg.S3Store(
            bucket="domain-kernel-outputs-example",
            prefix="artifacts/",
            region="eu-central-1",
            credentials="output_aws",
        ),
    },
    storage=cfg.Storage(artifact_store="artifacts"),
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

client_two = Client(config=configuration, model_gateway=gateway)
project = client_two.projects.get(key="pump-co")
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

Use Pydantic BaseModel for ClientConfiguration and its nested sections, and a
private Pydantic Settings BaseSettings model for the resolved runtime settings.
This separates declarative Python records from settings-source I/O. The loader
uses explicitly configured sources for the selected TOML or Python input and its
environment references. It must preserve the scoped dotenv and precedence rules
below instead of enabling BaseSettings' default environment overrides.

Apply a shared model policy throughout the configuration tree. For example, this
small schema illustrates the required validation behavior; it is not the complete
SDK configuration implementation:

```python
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigurationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )


class InMemoryProcessing(ConfigurationModel):
    mode: Literal["memory"] = "memory"
    max_source_bytes: Annotated[int, Field(strict=True, gt=0)] = 64 * 1024 * 1024
    max_concurrent_sources: Annotated[int, Field(strict=True, gt=0)] = 2
```

Here, zero or negative limits, booleans passed as integers, strings passed as
integers, an unsupported mode, and misspelled fields all fail validation. TOML
numeric and boolean literals must have the expected types. String paths and
explicitly referenced environment values need documented, source-specific parsing
before strict validation; this must not become general permissive coercion.

Use discriminated unions with explicit type/provider tags for database, reader,
parser, store, and credential configurations. Validate cross-references and
capability compatibility after validating those records. The SDK must reject:

| Invalid input | Required behavior |
| --- | --- |
| Misspelled or unknown configuration field | Report its field path; do not ignore it |
| Unknown adapter/provider discriminator | Reject it; do not choose a default adapter |
| Invalid limit, enum, or retention-policy combination | Reject it before adapter creation |
| Missing required environment reference | Name the field and variable; reveal no value |
| Unknown or incompatible credential reference | Reject the reader/store configuration |
| Unknown artifact-store reference | Reject storage configuration |
| Unsupported configured capability or missing required extra | Report the specific configuration/dependency error; never substitute another capability |

Invalid direct model construction raises a Pydantic ValidationError. Client
loading and binding must surface a typed, sanitized ConfigurationError and must
not produce a partially usable client. Defaults apply to omitted fields, not
invalid supplied values. The SDK must not create projects, provision storage,
download sources, or invoke inference while validating settings. Successful local
validation does not prove remote credentials or connectivity; authorization and
network failures must still stop the affected operation without a fallback.

Revalidate supplied model instances and capture a detached runtime snapshot.
`frozen=True` prevents attribute reassignment but does not recursively freeze
mutable dictionaries. Changing a caller's configuration mappings must not alter
an already initialized Client.

Public configuration keeps secret references; resolved settings use secret-aware
types and remain private. `hide_input_in_errors=True` protects printed errors but
does not remove raw inputs from every structured error representation. Sanitize
SDK error objects and exception chains; never expose raw validation input or
secret-bearing context. Custom validators must not echo secret values.

Pydantic Settings is a separate package from Pydantic and is not yet installed or
declared in this repository. It is required for the future loader. These examples
do not install it or implement that loader. Its source customization supports
this controlled-loading design: see
[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#customise-settings-sources).
Keep settings sources at the composition boundary and domain logic independent of
Pydantic Settings. Public models can emit JSON Schema for reference and tooling.

## TOML and dotenv files

TOML is a data format. Its parser does not load `.env` or expand `${VARIABLE}`.
Those behaviors must be provided by the SDK loader. Use explicit references so a
secret value never needs to appear in TOML:

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

The Pydantic Settings loader can use Python's
[tomllib](https://docs.python.org/3.13/library/tomllib.html) and an explicitly
configured TOML source, with
[python-dotenv's non-mutating dotenv_values](https://bbc2.github.io/python-dotenv/#load-configuration-without-altering-the-environment)
for dotenv parsing. Setting `interpolate=False` is part of the proposed loader
behavior. No loader or new runtime dependency is introduced by these examples.

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

For a minimal local deployment, the proposed defaults make this file sufficient:

```toml
schema_version = 1
```

The local reader defaults to the configuration directory. The longer local
example narrows it to `./data` and explicitly selects optional parsers. Named
reader paths must stay within their configured root or prefix. Parser options
such as sheets or pages remain available on typed source descriptors.

`parsers` select format adapters; `readers` locate inputs; `stores` select output
destinations. Selecting a PostgreSQL state backend does not move documents or
change their readers. Selecting S3 does not require PostgreSQL. Each optional
adapter requires its own installed dependency extra; these proposed adapter IDs
do not mean the extras already exist in `pyproject.toml`.

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

After explicitly creating `pump-co`, select it and use the configured reader:

```python
from domain_kernel import Client, Excel, PDF, ReaderLocation

client = Client(config="domain-kernel.toml", model_gateway=gateway)
project = client.projects.get(key="pump-co")

result = await project.discover(
    sources=[
        Excel(
            location=ReaderLocation(reader="inputs", path="components.xlsx"),
            sheets=("Components",),
        ),
        PDF(
            location=ReaderLocation(reader="inputs", path="production_manual.pdf"),
        ),
    ],
)

result
```

With the local example, these paths refer to files below `./data`. With either S3
example, they refer to objects below `manufacturing/` in the configured input
bucket. The source descriptors remain unchanged. Resolve the configured provider
and record its actual origin, version, and content digest when acquiring content.
The names `Excel`, `PDF`, and `ReaderLocation` illustrate typed format and location
contracts; their final public signatures remain open.

With the dotenv-enabled example, select `ReaderLocation(reader="manuals", path=...)`
for a file under the configured SharePoint folder. Choosing a reader selects its
configured credentials and scope; it does not change the source format descriptor.

The discovery result remains inspectable while review is pending. Submit decisions
through `project.review`; final approval and publication must still identify the
exact reviewed candidate. Once a model version has been approved and published,
an export can address a configured store:

```python
project.modeling.export(
    published_id=published_version.id,
    store="artifacts",
    path="exports/1.0.0.json",
    format="json",
)
```

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
an approved configured store. In-memory parsing must continue to satisfy the
existing adapter and no-spill requirements. See
[SDK_REQUIREMENTS.md](../../SDK_REQUIREMENTS.md) for the full constraints.
