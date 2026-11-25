# Repository documentation refactor research

Give an SDK evaluator a first success without an inference provider. Give a
developer or agent a way to trace the same kind of change into the code and
find the rules it must preserve. Let the notebook teach the longer journey,
with separate paths to read saved results, verify the workflow offline, and
run it against a live provider.

This proposal uses the `feat/document-discovery-workflow` checkout at
`6157429`. It builds on the [current ownership rules](../documentation.md#content-ownership)
and complements the [maintainer documentation research](maintainer-documentation-research.md),
which covers architecture prose, diagrams, and newcomer testing in more depth.
Public availability and reporting observations are from 25 November 2026.

## README: Get to a first success

[GitHub’s README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes#about-readmes)
says a README typically answers what the project does, why it is useful, how to
start, and where to get help. GitHub surfaces a root README unless one in
`.github` takes precedence. [Diátaxis](https://diataxis.fr/start-here/) separates
a practical lesson from task instructions, reference, and explanation. Neither
source prescribes a Domain Kernel README structure. Use that distinction to
give the README a short working path without copying the whole SDK guide.

1. **What it does.** Explain that you embed Domain Kernel in a Python
   application to review definitions and publish a versioned, portable model.
   Show a concrete input and output: a reviewer approves a change to the
   recruitment model, and a receiving application reads the result from a
   bundle file. Say where the SDK stops: the host owns permissions and
   operations; using a model provider to propose changes is optional.
2. **Quickstart.** Put the core, no-key path first. The
   [SDK quickstart source](../../apps/docs/src/app/quickstart/page.mdx) already
   documents `uv sync --locked --no-dev` and
   `uv run --locked --no-dev python -m examples.recruitment_quickstart` from
   the checkout. The [example](../../examples/recruitment_quickstart.py)
   reviews a correction and delivers two versioned bundles to a separate
   process; the consumer checks the file hashes and prints a purpose limit
   of two and then three. Present those lines as the expected result. This is
   not a notebook setup, and the example module requires the source tree.
3. **Where to go next.** Offer the SDK quickstart and reference where available,
   the [notebook guide](../../examples/notebooks/README.md),
   [architecture](../../ARCHITECTURE.md), [contribution rules](../../CONTRIBUTING.md),
   [private reporting](../../SECURITY.md), and [license](../../LICENSE).
   Keep a short pointer to [distribution and supply-chain verification](../releasing.md)
   rather than repeating the contributor environment and release procedures.
   Lead with surfaces a reader can actually open from the revision in view.

**Verified quickstart baseline.** In a fresh archive of `6157429`, the two
documented `uv` commands passed with `--offline` and Python 3.13.12. They
installed the core SDK without development dependencies or inference extras.
The separate consumer printed model version `1.0.0` with purpose maximum `2`
and model version `1.1.0` with maximum `3`. These are model versions, not SDK
release numbers. This validates the source path against the local dependency
cache, not a public package or a newcomer session.

**Installation evidence.** The Python Packaging User Guide distinguishes
[isolated environments, wheels, and source distributions](https://packaging.python.org/en/latest/tutorials/installing-packages/)
from the question of where those artifacts are available. Use the project's
[uv workflow](https://docs.astral.sh/uv/concepts/projects/sync/) rather than
copying PyPA's installer commands. [Local project metadata](../../pyproject.toml)
says `domain-kernel` version `0.1.0` and Python `>=3.13`; it does not prove a
release exists or that any release is supported. The [release guide](../releasing.md)
names GitHub Releases and says PyPI publishing is not configured. During this
research the [GitHub Releases page](https://github.com/matejpalenik/domain-kernel/releases)
reported no releases, and the [PyPI project URL](https://pypi.org/project/domain-kernel/)
returned HTTP 404. Keep the checkout path first until a distribution is
verified. When a release is available, test the exact wheel from that release
in a fresh environment outside the checkout. Use a standalone snippet or a
separately verified examples archive; don't assume the wheel ships the example
module. Keep installable-package and source-tree instructions distinct.

The root README is also the package’s long description because
`pyproject.toml` sets `readme = "README.md"`. The
[PyPA metadata specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/#readme)
defines that field; it does not guarantee GitHub-relative links and images
render on another host. [GitHub resolves relative links in repository Markdown](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes#relative-links-and-image-paths-in-markdown-files).
Inspect the built long description and check critical links in every intended
display context before switching the preferred install route.

## ARCHITECTURE: Show where to change the SDK

The [architecture reference](../../ARCHITECTURE.md#architecture-reference)
currently follows a lengthy, explicitly proposed API walkthrough.
Start instead with the supplier catalog: show a manual proposal and a proposal
drawn from a document, where they meet at review, and what a publication
hands to another application. Keep a short entry path for a Python developer
new to the SDK, with links into a detailed reference that owns the design and
invariants. Check the implementation against source and tests and label
proposed behavior next to the relevant claim.

Use [C4’s levels of zoom](https://c4model.com/diagrams) selectively: one view
for the host and its external dependencies, then a code map for component
responsibilities and allowed dependency directions. Do not draw the embedded
SDK as a separately deployed server. Use the
[arc42 runtime view](https://docs.arc42.org/section-6/) principle of a few
architecturally relevant scenarios, including consequential failures. Give
runtime sequences separate diagrams or prose; workflow order is not import
direction.

| Section | What a maintainer or agent needs |
| --- | --- |
| System context and ownership | What runs in the host process; who owns identity, review decisions and provider configuration; which stores and adapters do I/O; what an independent bundle consumer needs. |
| Lifecycle and package map | The vocabulary in context, the major state changes, and a link from each component’s responsibility to an entry symbol and its owning tests. Start at the [public exports](../../src/domain_kernel/__init__.py) and distinguish public API, service, domain rules, ports, and adapters. |
| Runtime traces | Follow manual review through publication and detached reading. Add a discovery branch that shows where an inference proposal enters review. For each handoff, name the input, owning component, saved state, and useful output. |
| Deep design reference | Retain the exact rules and rationale for evidence identity, review and replays, validation and publication, portable bundles and projections, dependency pins and model evolution, transactions and failure recovery, and extension points. Transfer SDK usage to its existing owner; keep a short snippet only when the call or order explains a rule. |

For a traceable rule, start at [`Model.publish()`](../../src/domain_kernel/modeling/api/model.py),
follow [`PublicationService.publish()`](../../src/domain_kernel/modeling/application/publication.py)
to [`require_current_publication()`](../../src/domain_kernel/modeling/domain/publications.py),
and then open `test_preparation_and_exact_releases_replay_across_clients` in the
[publication tests](../../tests/integration/modeling/test_publication.py). The test
distinguishes replaying an exact previous intent from trying to create a new
version after the workspace changes. For the receiving side, pair
`DomainModelBundle.deserialize()` with `test_bundle_round_trip_uses_only_core_types`
in the [portable bundle tests](../../tests/integration/modeling/test_portable_bundle.py).
Remove the old implementation sequence after mapping any still-relevant rules
or test requirements to their owners. Keep what maintainers need to preserve,
not the order in which already implemented capabilities were planned.

## Notebook: Separate reading, reproducible checks, and live operation

[Project Jupyter’s nbclient guide](https://nbclient.readthedocs.io/en/latest/client.html)
shows programmatic execution with a selected kernel, working directory, and
timeout. [nbconvert](https://nbconvert.readthedocs.io/en/latest/usage.html#html)
can produce a static HTML rendering. [GitHub’s notebook view](https://docs.github.com/en/repositories/working-with-files/using-files/working-with-non-code-files#working-with-jupyter-notebook-files-on-github)
renders `.ipynb` as static HTML; it does not run the Python controls. Those are
tool capabilities. Which outputs count as evidence is our documentation choice.

| Path | What to document and verify |
| --- | --- |
| Read without a kernel | At the research revision, the [saved HTML](https://github.com/matejpalenik/domain-kernel/blob/615742966afe7abb358cea427603104426a2efd0/examples/notebooks/domain-kernel-tour.html) labelled its outputs as simulated, using a synthetic PDF and scripted replies. The repository link identified a file, not a verified hosted render. The configured Pages root, quickstart, tour and reference returned HTTP 404 during this research. |
| Verify without credentials | The [test harness](../../tests/support/notebook/tour.py) supplies controlled inputs at the external boundaries; the [integration test](../../tests/integration/tooling/notebook/test_notebook_preview.py) exercises notebook execution and offline restart. Require a clean kernel and disposable workspace, validate the emitted bundle in a file-only process, and check that replay adds no provider attempts. Call this a test of the SDK workflow, not live inference evidence. |
| Run against live inputs | Put exact extras, kernel/interpreter, working directory, publisher pin, output path, network and provider requirements, and possible cost in the [run guide](../../examples/notebooks/README.md) before **Run All**. Explain how to resume the same workspace versus starting a new run. Keep secrets and sensitive inputs out of saved outputs. Show what to inspect when discovery rejects a response, and distinguish a manually authored handoff from accepted discovery proposals. |

At the research revision, the website guide and output writer expected
outputs from a verified live run while the saved HTML declared simulation.
The [acceptance record](../../examples/notebooks/VALIDATION.md)
describes a live run whose response produced no draft, followed by a manually
authored published handoff. That record neither proves successful live
extraction nor establishes the provenance of the saved outputs. The focused
offline restart test passed for the valid fixture: a fresh kernel reopened the
complete model with zero new provider attempts. This research did not run the
live provider or refresh any outputs.

## CONTRIBUTING and SECURITY: Put the next action first

[GitHub surfaces `CONTRIBUTING.md`](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors#about-contributing-guidelines)
when readers open issues or pull requests and on the Contribute page. Keep
the repository’s [contributor guide](../../CONTRIBUTING.md) at the root. Start
with where to discuss or report an ordinary change, where to report a
vulnerability privately, and how to prepare a first SDK change. Separate the
Python path from optional notebook, website, and adapter setup. Give a small
change-to-check table, then the PR and review requirements. Link to
[engineering conventions](../../AGENTS.md) for shared rules, the
[website guide](../documentation.md) for website operations,
[security policy](../../SECURITY.md) for dependency policy, and the
[release guide](../releasing.md) for maintainer-only steps. Preserve policy
without copying every command into both the README and contributor guide.

[GitHub’s security-policy guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/add-security-policy)
asks for supported versions and how to report vulnerabilities.
[Private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
is a separate repository setting. The [public Security Policy](https://github.com/matejpalenik/domain-kernel/security/policy)
rendered and the [Advisories page](https://github.com/matejpalenik/domain-kernel/security/advisories)
showed **Report a vulnerability** during this research. No report was sent;
the maintainer still needs to confirm the monitored route and receipt process.

Keep [SECURITY.md](../../SECURITY.md) easy for a reporter to scan: private
entry point and verified fallback, information to include without secrets or
customer data, supported versions or a clear statement that no period is
guaranteed, and what happens next. These promises belong to the maintainer,
not GitHub. Resolve the difference between the README’s pre-alpha badge, the
security policy’s pre-alpha and best-effort wording, and the metadata’s
`Production/Stable` classifier before changing support language. Ask the
maintainer to confirm the support scope, contact and any response commitment.
Do not infer them from `0.1.0`, a classifier, or passing CI. Leave established
dependency and compliance limits intact; link to
[settings definitions](../../.github/security-settings.md) and release
verification for operator detail. Do not equate checked-in settings with a
current administrator readback or an SBOM with a compliance claim.

## Refactor order and acceptance

| Order | Change | Acceptance check |
| --- | --- | --- |
| 1 | Verify the baseline and decide what each surface owns. | Confirm public install artifacts, Pages destinations, and the security contact/support policy (or mark them unverified). Inventory inbound links before moving headings or procedures. At the research revision, `CONTRIBUTING.md` linked to the missing `README.md#quickstart` heading. |
| 2 | Make the no-key README path work first, then link to detail. | Give a new Python developer the exact commands and a clean Python environment. Run against the documented checkout, or against verified release bytes if the route advertises a distribution. Without a key or producer database, a separate process opens both bundles and reports the expected versioned change; the reader can explain the result. |
| 3 | Reorder architecture around context, code and runtime, then retain the deep contracts. | A newcomer can follow an entry point to a service, invariant and owning test, and explain why stale publication is rejected while exact replay still works. Verify relocated rules, code links and rendered diagrams. |
| 4 | Align the notebook run guide, labels and saved reading path. | Execute the offline fixture path from a fresh kernel and verify restart and detached bundle reading without provider calls. Only with separate authorization, verify the live path and document actual provider outcomes, including any rejected response, before changing live-evidence claims or artifacts. |
| 5 | Finish contributor and reporter routes; review all links together. | From the root, find the first contribution check and the private reporting route without needing to run the tour. Have the maintainer approve support/contact wording; verify headings and destinations against the branch and intended published surfaces. No publication is necessary to review the refactor. |

These were research recommendations. For the first pass, the maintainer chose
a short SDK usage example rather than a terminal demo for the README, and
retired the standalone HTML and website tour while keeping the interactive
notebook and portable archive.
