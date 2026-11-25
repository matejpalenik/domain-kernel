# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: tour_id,tags
#     formats: ipynb,py:percent
#     notebook_metadata_filter: kernelspec,language_info,jupytext
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.6
#   kernelspec:
#     display_name: domain-kernel (3.13.x)
#     language: python
#     name: python3
#   language_info:
#     codemirror_mode:
#       name: ipython
#       version: 3
#     file_extension: .py
#     mimetype: text/x-python
#     name: python
#     nbconvert_exporter: python
#     pygments_lexer: ipython3
#     version: 3.13.12
# ---

# %% [markdown] tour_id="tour-introduction"
# # From AI Act evidence to a model you can ship
#
# Build a model for the developer designing a recruitment application. They need to tell
# technical documentation from instructions for use, see which fields to store, and trace a
# definition back to the AI Act. You will hand them a reviewed model and a JSON Schema.
#
# With Python 3.13 or newer, run this from the repository root:
#
# ```sh
# uv sync --locked --group notebook --extra documents --extra inference --extra discovery-workflow
# ```
#
# Put `OPENAI_API_KEY` in the Git-ignored root `.env` and select the project's
# `.venv/bin/python` kernel. Choose **Restart Kernel** after updating the environment, then
# **Run All**. The first live run downloads the publisher PDF and uses paid GPT-6 Luna
# calls to orient, draft and review. Run All again in the same workspace to reopen
# the saved result. The saved walkthrough outputs are simulated using a synthetic PDF
# and scripted provider replies. They are not a live run or a benchmark.

# %% [markdown] tour_id="c3-introduction"
# <a id="evidence"></a>
#
# ## Read the evidence
#
# Verify the publisher's PDF, then configure the SDK to read it with Docling and retain
# the extracted text in SQLite.

# %% tags=["sdk"] tour_id="c1-sdk-original"
import sys
from pathlib import Path

here = Path.cwd()
checkout = next(
    (path for path in (here, *here.parents) if (path / "pyproject.toml").is_file()),
    here,
)
if str(checkout) not in sys.path:
    sys.path.insert(0, str(checkout))

from examples.notebooks._preview.workspaces import select_demo_workspace
from examples.notebooks.originals import load_originals

workspace = select_demo_workspace(name="recruitment-v23", directory=checkout)
downloads = workspace / "sources"
pdf = load_originals(directory=downloads, identifiers=["ai-act-en"], download=True)["ai-act-en"]
print("Original English Official Journal edition · 12 July 2024")
print(f"Verified PDF: {pdf.relative_path}")
print(pdf.digest.value)

# %% tags=["sdk"] tour_id="c1-sdk-client"
import os

from domain_kernel import (
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DoclingParser,
    LangGraphDiscoveryGateway,
    LiteLLMGateway,
    ModelKind,
    ModelNotFoundError,
    ProjectNotFoundError,
)
from domain_kernel.configuration import FilesystemReader, InferencePolicy, Retention
from examples.notebooks.live_campaign import CampaignBudget, CampaignGateway
from examples.notebooks.live_discovery import official_api_key

_ = os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
luna = LiteLLMGateway(
    model="openai/gpt-6-luna",
    api_key=official_api_key(),
    reasoning_effort="none",
    max_output_tokens=8192,
)
budget = CampaignBudget(path=workspace / "inference.sqlite3", max_input=950_000, max_output=95_000)
client = Client(
    config=ClientConfiguration(
        base_dir=workspace,
        readers=[FilesystemReader(name="inputs", root=downloads.resolve())],
        retention=Retention(extracted_text=True),
        inference=InferencePolicy(timeout_seconds=1200.0, max_input_bytes=750_000),
        model_gateway=LangGraphDiscoveryGateway(
            gateway=CampaignGateway(gateway=luna, budget=budget, stage="notebook-full-act"),
            directory=workspace / "workflow",
            profile="openai/gpt-6-luna/none/8192",
        ),
    ),
    integrations=ClientIntegrations(format_parsers={"pdf": DoclingParser()}),
)
author, reviewer, publisher = "demo:developer", "demo:mira", "demo:release-owner"
try:
    project = await client.get_project(name="employment-policy")
except ProjectNotFoundError:
    project = await client.create_project(name="employment-policy", actor=author)
try:
    model = await project.get_model(name="ai-in-recruitment")
except ModelNotFoundError:
    model = await project.create_model(
        name="ai-in-recruitment",
        description=(
            "Describe how AI is used in recruitment and selection, who is involved, "
            "and what responsibilities they have."
        ),
        kind=ModelKind.OBSERVED,
        actor=author,
    )
print(f"SQLite workspace: {workspace.relative_to(checkout)}")
print(f"Model: {model.info.name} · Discovery: {luna.model}")

# %% [markdown] tour_id="c3-sdk-docling-introduction"
# Ingest the whole PDF. The file stays in `sources/`. SQLite stores the extracted page
# text and its citations. Read a page through a new client to see what the SDK saved.

# %% tags=["sdk"] tour_id="c3-sdk-docling"
from domain_kernel import PDF, DocumentSpan

act = await project.ingest_source(
    name="english-ai-act",
    source=PDF(path=pdf.relative_path, expected_hash=pdf.digest),
    actor=author,
    idempotency_key="ingest-full-english-ai-act",
)
pages = {
    item.locator.page: item
    for item in act.evidence
    if isinstance(item.locator, DocumentSpan) and item.locator.section is None
}
retained = Client(config=ClientConfiguration(base_dir=workspace))
retained_project = await retained.get_project(name=project.name)
article_13 = await retained_project.get_evidence(evidence=pages[59])

print(f"Saved text from {len(pages)} PDF pages in SQLite")
print(f"Docling version: {pages[59].processing.parser_version}")
print("PDF page 59 · full text read back from SQLite")
print(article_13.excerpt)

# %% [markdown] tour_id="c4-introduction"
# <a id="draft"></a>
#
# ## Discover concepts and relationships
#
# Pass the source revision to `discover()`. Discovery uses the model description as its purpose.
# For a long packet it orients across the source, then retrieves passages and checks the
# draft against the purpose. Inspect the proposals and exact evidence before editing them.
#
# For a closer look at citations and run failures, open
# [Discover a recruitment model](document-discovery.ipynb).

# %% tags=["sdk"] tour_id="c4-sdk-resume-run"
from domain_kernel import RelationshipDefinition

before = budget.usage()
run = await model.discover(
    sources=[act.revision],
    actor=author,
    idempotency_key="discover-recruitment-v23",
)
if run.failures:
    reasons = ". ".join(failure.message for failure in run.failures)
    message = f"Discovery {run.id.value} is {run.status.value}. {reasons}"
    print(message)
    if run.discovery_id is None:
        print("No validated draft. The handoff below uses the sample reviewer's source evidence.")
cases = [case async for case in model.iter_review_cases(run_id=run.id)]
usage = budget.usage()
print(f"Discovery source: {len(pages)} captured PDF pages")
print(f"Provider attempts this run: {usage.attempts - before.attempts}")
print(f"Saved Luna input/output tokens: {usage.input_tokens:,}/{usage.output_tokens:,}")
print(f"v23 discovery through LiteLLM: {run.status.value} · {len(cases)} review cases")
names = {item.id: item.display_name for case in cases for item in case.definitions}
for case in cases:
    for definition in case.definitions:
        locations = ", ".join(
            str(item.locator.page)
            for item in case.evidence
            if isinstance(item.locator, DocumentSpan)
        )
        print(f"\n{case.status.value} · {definition.name} · PDF pages {locations}")
        print(definition.meaning)
        if isinstance(definition.body, RelationshipDefinition):
            print(
                f"{names.get(definition.body.source_concept_id, 'Approved concept')} → "
                f"{names.get(definition.body.target_concept_id, 'Approved concept')}"
            )

# %% [markdown] tour_id="c6-introduction"
# <a id="review"></a>
#
# ## Review the model
#
# For this release, the sample reviewer selects the
# meanings needed by a developer implementing instructions for use. The release also
# distinguishes technical documentation and records who supplies the instructions.
# Other suggestions remain visible in the discovery run and are marked outside this release.

# %% tags=["sdk"] tour_id="c6-sdk-review-comparison"
from domain_kernel import (
    AttributeDefinition,
    CaseStatus,
    ConceptDefinition,
    EditDefinition,
    Model,
    ReviewAction,
    ReviewCase,
)
from examples.notebooks.tour_walkthrough import select_concept


async def review_case(
    *, model: Model, case: ReviewCase, decision: ReviewAction, actor: str
) -> None:
    """Preview a decision and record it once under the sample reviewer's name."""
    case = await model.get_review_case(case_id=case.id)
    name = case.definitions[0].name
    if case.status is CaseStatus.PENDING:
        impact = await model.preview_changes(case=case, decision=decision)
        print(f"Preview {name} · {len(impact.definition_changes)} definition changes")
        receipt = await model.decide_review(
            case=case,
            decision=decision,
            actor=actor,
            idempotency_key=f"review-{case.id.value}",
        )
        print(f"Reviewed {name} · {actor} · decision {receipt.decision_id.value}")
    else:
        print(f"Reopened review of {name} · {case.status.value}")


concepts = [
    (
        "technical-documentation",
        "Technical documentation",
        "Documentation kept current to support assessment of a high-risk system.",
        (58,),
    ),
    (
        "instructions-for-use",
        "Instructions for use",
        "Information the provider supplies to help the deployer use the system.",
        (59, 60),
    ),
    (
        "provider",
        "Provider",
        (
            "The person or body that develops an AI system or has it developed, then places "
            "it on the market or puts it into service under its own name or trademark."
        ),
        (46,),
    ),
]
selected = set()
for name, title, meaning, cited_pages in concepts:
    case = await select_concept(
        model=model,
        cases=cases,
        name=name,
        title=title,
        meaning=meaning,
        evidence=[pages[page] for page in cited_pages],
        actor=author,
    )
    selected.add(case.id)
    fields = (
        [AttributeDefinition.string(name="logging-mechanisms", display_name="Logging mechanisms")]
        if name == "instructions-for-use"
        else []
    )
    await review_case(
        model=model,
        case=case,
        decision=EditDefinition(
            definition_id=case.definitions[0].id,
            name=name,
            display_name=title,
            meaning=meaning,
            body=ConceptDefinition(attributes=fields),
            reason="Use the meaning and application shape checked against the cited Act pages.",
        ),
        actor=reviewer,
    )

# %% [markdown] tour_id="c7-introduction"
# Connect the provider to the instructions it supplies. Record the *where relevant*
# qualification as a cited rule alongside the field.

# %% tags=["sdk"] tour_id="c7-sdk-review-locator"
from domain_kernel import (
    Accept,
    CardinalityBounds,
    Exclude,
    RelationshipCardinality,
    RuleDefinition,
)

provider = await model.get_concept(name="provider")
instructions = await model.get_concept(name="instructions-for-use")
logging_page = await retained_project.get_evidence(evidence=pages[60])
logging_text = logging_page.excerpt
start = logging_text.lower().rindex("where relevant")
print("Logging passage · AI Act PDF page 60")
print(logging_text[start:].split("Article 14", maxsplit=1)[0].strip())
qualification = (
    "Where relevant, the instructions describe mechanisms for collecting, storing "
    "and interpreting logs."
)
additions = [
    (
        "supplies-instructions",
        "Supplies instructions",
        "The provider supplies instructions for use to the deployer.",
        RelationshipDefinition(
            source_concept_id=provider.id,
            target_concept_id=instructions.id,
            cardinality=RelationshipCardinality(
                incoming=CardinalityBounds(maximum=None),
                outgoing=CardinalityBounds(maximum=None),
            ),
        ),
        (59, 62),
    ),
    (
        "logging-qualification",
        "Logging qualification",
        qualification,
        RuleDefinition(statement=qualification),
        (60,),
    ),
]
for name, title, meaning, body, cited_pages in additions:
    case = await model.propose_definition(
        name=name,
        display_name=title,
        meaning=meaning,
        body=body,
        evidence=[pages[page] for page in cited_pages],
        reason="Add application structure grounded in the inspected PDF.",
        actor=author,
        idempotency_key=f"propose-{name}",
    )
    await review_case(
        model=model,
        case=case,
        decision=Accept(reason="The cited passage supports this addition."),
        actor=reviewer,
    )

for case in cases:
    if case.id not in selected:
        await review_case(
            model=model,
            case=case,
            decision=Exclude(
                scope_text="The documentation handoff for the recruitment application",
                reason="The sample reviewer selected other evidence for this release.",
            ),
            actor=reviewer,
        )

# %% [markdown] tour_id="c8-introduction"
# <a id="publish"></a>
#
# ## Publish and open the complete model
#
# Publish the reviewed definitions as version `1.0.0`. Export the bundle, the file the
# receiving developer can open independently.

# %% tags=["sdk"] tour_id="c2-sdk-publish"
prepared = await model.prepare_publication(actor=publisher, idempotency_key="prepare-1.0.0")
release = await model.publish(
    publication=prepared,
    version="1.0.0",
    reason="Ship the reviewed recruitment documentation model.",
    actor=publisher,
    idempotency_key="publish-1.0.0",
)
delivery = await model.export(
    bundle=release,
    store="artifacts",
    path="recruitment-1.0.0.bundle.json",
    actor=publisher,
    idempotency_key="export-1.0.0",
)
artifact_directory = workspace / ".domain-kernel" / "artifacts"
bundle_file = artifact_directory / delivery.key
print(f"Published {release.version} by {publisher}")
print(bundle_file.relative_to(checkout))
print(delivery.content_hash.value)

# %% tags=["sdk"] tour_id="c9-sdk-portable"
from domain_kernel import DomainModelBundle
from examples.notebooks.tour_walkthrough import show_model

bundle = DomainModelBundle.deserialize(
    payload=bundle_file.read_bytes(),
    expected_hash=delivery.content_hash,
)
show_model(bundle=bundle)

# %% [markdown] tour_id="c9-sdk-json-schema-introduction"
# Look up the instructions and validate a sample record with the exported JSON Schema.
# The bundle also gives the application the reviewed qualification and its PDF citation.

# %% tags=["sdk"] tour_id="c9-sdk-json-schema"
import json
from urllib.parse import unquote

from jsonschema import Draft202012Validator

from domain_kernel import Iri, JsonSchemaProjectionRequest

instructions = bundle.get_concept(name="instructions-for-use")
field = instructions.get_attribute(name="logging-mechanisms")
schema_delivery = await model.export(
    bundle=bundle,
    request=JsonSchemaProjectionRequest(
        root=instructions,
        base_iri=Iri(value="https://example.org/recruitment/"),
    ),
    store="artifacts",
    path="instructions-for-use.schema.json",
    actor=publisher,
    idempotency_key="export-schema-1.0.0",
)
schema_file = artifact_directory / schema_delivery.key
schema = json.loads(schema_file.read_bytes())
shape = schema["$defs"][unquote(schema["$ref"].removeprefix("#/$defs/"))]
record = {
    "@id": "https://example.org/records/screening-instructions",
    "@type": shape["properties"]["@type"]["const"],
    field.name: "The application records edits to candidate scores.",
}
Draft202012Validator(schema).validate(record)
print(json.dumps(record, indent=2))
print("Sample instructions record passes the exported schema.")
print(schema_file.relative_to(checkout))

# %% [markdown] tour_id="tour-completion"
# Send the bundle and its hash with the schema and sample record. To add a separately
# attributed source and compare releases, follow the
# [Commission guidance recipe](README.md#live-discovery).
