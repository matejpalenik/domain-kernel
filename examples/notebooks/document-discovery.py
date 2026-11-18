# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: tour_id
#     formats: ipynb,py:percent
#     notebook_metadata_filter: kernelspec,jupytext
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.6
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown] tour_id="scope"
# # Discover a recruitment model from the AI Act
#
# You are building a recruitment application. Which roles and relationships does the source
# support? Discover them from the complete pinned English Official Journal PDF, then inspect the
# evidence behind each draft. All proposals stay pending for review.
#
# From a clone, install the notebook environment.
#
# ```sh
# uv sync --locked --group notebook --extra documents --extra inference --extra discovery-workflow
# ```
#
#  Put `OPENAI_API_KEY` in the repository-root `.env`, select the project kernel and **Run
# All**. The first run downloads the PDF as needed and makes multiple paid Luna calls. Restart
# in the same workspace to reopen the result. The local stage journal contains source quotations
# and provider responses.

# %% tour_id="configure"
import json
import sys
from pathlib import Path

root = next(
    path for path in (Path.cwd(), *Path.cwd().parents) if (path / "pyproject.toml").is_file()
)
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from domain_kernel import PDF, DocumentSpan
from examples.notebooks.document_discovery import configured_client, open_recruitment_model
from examples.notebooks.originals import load_originals

workspace = root / "local/staged-recruitment-discovery"
originals = root / "local/notebook-tour/recruitment-default-discovery/sources"
original = load_originals(directory=originals, identifiers=["ai-act-en"], download=True)[
    "ai-act-en"
]
client, budget, graph = configured_client(workspace=workspace, originals=originals)
actor = "demo:discovery-reader"
project, model = await open_recruitment_model(client=client, actor=actor)
print(model.info.description)
print(original.digest.value)

# %% [markdown] tour_id="read"
# ## Read the source
#
# Docling groups native document items by structure and token budget. The SDK retains those
# chunks and separately addressable page text in SQLite. Read an original page for comparison.

# %% tour_id="capture"
source = await project.ingest_source(
    name="english-ai-act",
    source=PDF(path=original.relative_path, expected_hash=original.digest),
    actor=actor,
    idempotency_key="ingest-v1",
)
pages = {
    e.locator.page: e
    for e in source.evidence
    if isinstance(e.locator, DocumentSpan) and e.locator.section is None
}
print(f"{len(pages)} physical pages")
print((await project.get_evidence(evidence=pages[127])).excerpt)

# %% [markdown] tour_id="run"
# ## Discover and verify
#
# Pass the revision to the SDK. The executor extracts claims, checks omissions, verifies their
# quotations and meaning, and reviews relationship endpoints after resolving aliases. The model
# description supplies the recruitment scope.

# %% tour_id="discover"
before = budget.usage()
run = await model.discover(
    sources=[source.revision], actor=actor, idempotency_key="discover-verified-v3"
)
if run.failures:
    raise RuntimeError([(f.code, f.issue.path, f.message) for f in run.failures])
cases = [case async for case in model.iter_review_cases(run_id=run.id)]
print(f"{len(cases)} review cases · {run.status.value}")
print(f"New provider attempts this execution: {budget.usage().attempts - before.attempts}")

# %% [markdown] tour_id="results"
# ## Inspect the discovered model
#
# Each row is a proposal from this run. Follow the citations to check the meaning, including any
# conditions or exceptions. Review findings include statements the verifier withheld.

# %% tour_id="claims"
audit = json.loads((graph.directory / f"{run.id.value}.json").read_bytes())
for claim in audit["claims"]:
    print(f"\n{claim['kind']} · {claim['title']}")
    if claim["kind"] == "relationship":
        print(f"{claim['source']} → {claim['target']}")
    print(claim["meaning"])
    for part in [claim, *claim["conditions"], *claim["exceptions"]]:
        if "text" in part:
            print(part["text"])
        for anchor in part["evidence"]:
            locator = audit["locators"][anchor["citation"] - 1]["locator"]
            print(f"  {locator} · {anchor['quote']}")

# %% tour_id="findings"
from collections import Counter

print("Findings by review stage", dict(Counter(item["stage"] for item in audit["findings"])))
for component in audit["components"]:
    print(", ".join(component))
