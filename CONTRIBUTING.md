# Contributing to Domain Kernel

Thank you for your interest in contributing to Domain Kernel.

We welcome contributions that improve the SDK's functionality, reliability, discovery quality, documentation and developer experience.

Whether you are fixing a bug, improving documentation or proposing a new capability, this guide explains how to get started and meet the project's engineering standards.

## Ways to contribute

Domain Kernel is under active development. Contributions are particularly welcome in the following areas:

- **Discovery and evaluation.** Improve the quality of discovered domain models, evaluation methodologies and benchmark coverage.
- **Integrations.** Extend support for document formats, model providers, storage adapters and interoperability standards.
- **SDK development.** Improve functionality, performance, reliability and developer experience.
- **Testing.** Expand test coverage, identify edge cases and improve verification of SDK behaviour.
- **Documentation and examples.** Make Domain Kernel easier to understand, use and integrate into applications.

Report suspected security vulnerabilities privately using the process described in [SECURITY.md](SECURITY.md).

Use [GitHub Issues](https://github.com/matejpalenik/domain-kernel/issues) to report bugs, suggest improvements or discuss new capabilities.

When reporting a bug, include the affected version or commit, the expected and observed behaviour, and a minimal reproduction.

### Before starting

Small bug fixes, documentation improvements and additional tests can generally be submitted directly as pull requests.

For larger contributions, open an issue first to discuss the proposed approach. This is particularly important for changes to public APIs, architectural boundaries, dependency requirements or discovery behaviour.

Early discussion helps ensure that contributions align with the project's direction and avoids unnecessary implementation work.

The following resources will help you understand the project:

| Resource | Description |
|---|---|
| [README.md](README.md) | Introduction, product rationale and SDK quickstart. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architectural decisions, component boundaries and links to the detailed contracts. |
| [AGENTS.md](AGENTS.md) | Shared engineering standards and repository conventions. |
| [Testing verification map](.agents/skills/domain-kernel-testing/references/verification-map.md) | Testing requirements, tooling and evidence boundaries. |
| [SECURITY.md](SECURITY.md) | Security policies and dependency management requirements. |

## 1. Set up your development environment

### Prerequisites

| Tool | Requirement |
|---|---|
| Git | Required for repository development. |
| Python | 3.13 or 3.14. |
| [uv](https://docs.astral.sh/uv/) | Version pinned in `mise.toml`. |
| [mise](https://mise.jdx.dev/) | Recommended for managing pinned development tools. |
| Node.js | Version pinned in `mise.toml`, required for repository-level tooling. |
| pnpm | Version pinned in `mise.toml`, required for repository-level tooling. |

Node.js and pnpm are not SDK runtime dependencies. Python SDK development can begin using Python and uv alone. The full contribution workflow also uses JavaScript-based tooling for repository checks, commit validation and documentation development.

### Clone the repository

Fork the repository on GitHub and clone your fork.

```sh
git clone https://github.com/YOUR_USERNAME/domain-kernel.git
cd domain-kernel

git remote add upstream https://github.com/matejpalenik/domain-kernel.git
git switch -c feat/my-contribution
```

Contributors with repository write access may clone the main repository directly.

### Install development tools

The repository provides a `mise.toml` file containing pinned development tool versions.

If you use mise, install the configured tools:

```sh
mise install
```

Otherwise, install the required versions manually using the versions specified in `mise.toml`.

### Install Python dependencies

Install the SDK and its development dependencies using the committed lockfile:

```sh
uv sync --locked
```

Verify your installation:

```sh
uv run --locked pytest tests/unit/shared
```

This runs the shared contract tests without requiring optional SDK adapters.

Install additional adapter extras only when they are relevant to your contribution.

### Configure repository tooling

Install the JavaScript workspace dependencies and configure the Git hooks:

```sh
pnpm install --frozen-lockfile

uv run --locked pre-commit install \
    --hook-type pre-commit \
    --hook-type commit-msg
```

The pre-commit hooks enforce repository hygiene and applicable quality checks. The commit-message hook validates Conventional Commit messages.

For specialized development environments, follow the relevant setup guide:

| Area | Setup instructions |
|---|---|
| Documentation website | [Website development](docs/documentation.md#set-up-and-run) |
| Interactive notebooks | [Notebook development](examples/notebooks/README.md#run-from-a-checkout) |
| Optional SDK adapters | [Testing verification map](.agents/skills/domain-kernel-testing/references/verification-map.md) |

Keep dependency installations locked unless intentionally modifying the dependency graph.

## 2. Engineering standards

Domain Kernel follows strict engineering standards to keep the SDK predictable, maintainable and suitable for integration into larger applications.

[AGENTS.md](AGENTS.md) and the applicable repository skills define the detailed engineering requirements. The [architecture overview](ARCHITECTURE.md) explains system boundaries. Find the detailed requirement in the [contract index](docs/architecture/README.md).

### Architecture

When contributing to the SDK:

- **Respect component boundaries.** Keep responsibilities within the components and layers that own them.
- **Preserve public contracts.** Avoid unintended changes to public APIs, exported types and documented behaviour.
- **Keep the core lightweight.** Place optional integrations and their dependencies in the appropriate adapter packages.
- **Use explicit contracts.** Prefer strongly typed interfaces and clearly defined responsibilities.
- **Preserve evidence and review semantics.** Changes to discovery, review and publication must respect the SDK's evidence and decision boundaries.

Discuss significant architectural changes before implementation.

### Code quality

Domain Kernel uses Ruff for Python linting and formatting, and BasedPyright for static type checking.

Resolve linting and typing issues at their source rather than suppressing diagnostics to make checks pass.

Any necessary exception must be narrow, documented and justified.

Follow the conventions defined in `AGENTS.md`, the repository skills and the project configuration.

### Testing

Include meaningful tests for new functionality, bug fixes and behavioural changes.

| Test type | Location | Purpose |
|---|---|---|
| Unit tests | `tests/unit/` | Fast, deterministic verification of individual behaviours and contracts. |
| Integration tests | `tests/integration/` | Verification of persistence, optional adapters and other integration boundaries. |
| Formal checks | `tests/formal/` | Bounded models for guarantees that are hard to exercise; pair them with an SDK regression. |

Within each suite, group checks by the slice that owns the behavior. In unit tests,
use the owning layer when useful. For example, source format rules belong in
`tests/unit/sources/domain/`, and source capture through the SDK belongs in
`tests/integration/sources/`. Put only complete consumer workflows in
`tests/integration/journeys/`. Keep checks for notebooks, documentation and
benchmarks under the relevant suite's `tooling/` directory. Keep test-local
doubles beside their tests and put reused doubles in named modules under
`tests/support/`. Scope fixtures to the smallest suite that needs them.

Integration tests must use the `integration` marker. Ensure the required optional dependencies are provisioned in the CI jobs that execute them.

Verify changed SDK behaviour through its public entry points wherever applicable.

Distinguish deterministic fixture-based verification from live provider evidence. Passing a test against controlled model responses does not establish the quality of live discovery.

Use the Python 3.13 SDK job to compare statement and branch coverage. It runs the SDK
suite against SQLite and disposable PostgreSQL, including Python subprocesses. The job summary
lists the selected test and skip counts. Download `sdk-coverage` for the JSON and HTML reports.
Python 3.14 checks compatibility; notebook and provisioned-asset checks have their own evidence.
Compare only runs with the same test selection, adapters and coverage configuration.
There is no minimum threshold. Add tests that protect behavior, not just lines.

## 3. Run the quality checks

Domain Kernel provides focused quality checks for different areas of the repository.

Run the checks applicable to your contribution:

| What you changed | Command | Verification |
|---|---|---|
| Python SDK | `pnpm check:sdk` | Python linting, formatting, strict typing and SDK tests. |
| Notebooks or notebook helpers | `pnpm check:notebook` | Source pairing, evidence ledger and notebook execution. |
| Documentation website | `pnpm check:docs` | Formatting, linting, typing, content, static build and browser behaviour. |
| Multiple areas | `pnpm check` | All three verification groups. |
| Dependencies | See [Managing dependencies](#4-managing-dependencies). | Lockfile integrity, vulnerability audits and affected checks. |
| GitHub Actions | See [Updating GitHub Actions](#updating-github-actions). | Workflow and action provenance verification. |

Start with focused tests during development, then run the applicable verification group before submitting your changes.

### Python-only development

During Python development, individual checks can be run directly without pnpm:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest tests/unit/shared
```

Replace the shared test path with the tests relevant to your changes.

For complete SDK verification, use `pnpm check:sdk`, which also runs the configured static type checks.

See the [testing verification map](.agents/skills/domain-kernel-testing/references/verification-map.md) for the full verification requirements and optional dependencies.

### Python compatibility

CI verifies the SDK against Python 3.13 and 3.14.

When changing version-sensitive functionality, repeat the relevant checks under both Python versions.

```sh
uv run --locked --python 3.13 pytest tests/unit/shared
uv run --locked --python 3.14 pytest tests/unit/shared
```

Adjust the test selection to match the affected functionality.

### Notebook verification

Notebook checks use controlled test inputs to verify execution, source pairing and evidence handling.

CI also exercises Jupyter Notebook and JupyterLab in browser environments.

These checks do not establish the quality of live model inference. Live discovery evidence must be evaluated and reported separately.

### Repository-wide checks

Before opening a pull request, run:

```sh
uv run --locked pre-commit run --all-files
```

Review any changes made automatically by repository hygiene hooks.

Ruff formatting hooks operate in check-only mode. To format Python files explicitly, run:

```sh
uv run --locked ruff format .
```

CI runs the Python and repository hygiene checks in the Python matrix and delegates JavaScript verification to the required documentation job.

All verification commands must preserve the committed dependency lockfiles.

## 4. Managing dependencies

Domain Kernel uses `uv` for Python dependency management and `pnpm` for JavaScript workspace dependencies.

Dependency changes must be intentional, reproducible and consistent with the [security policy](SECURITY.md).

### Python dependencies

Add or remove dependencies using uv:

```sh
uv add PACKAGE
uv remove PACKAGE
```

Add an optional integration dependency to the appropriate extra:

```sh
uv add --optional EXTRA PACKAGE
```

Update an existing dependency intentionally:

```sh
uv lock --upgrade-package PACKAGE
uv sync --locked
```

After modifying the dependency graph, review the complete lockfile diff and run:

```sh
uv lock --check
uv audit --locked
```

Run the quality checks applicable to the affected components.

Commit `pyproject.toml` and `uv.lock` together when dependency declarations and resolution change.

Never edit `uv.lock` manually.

### JavaScript dependencies

Use `pnpm` to add, remove or update JavaScript workspace dependencies.

```sh
pnpm add PACKAGE
pnpm remove PACKAGE
```

Run these commands in the appropriate workspace package.

Commit the affected package manifests and `pnpm-lock.yaml` together.

Verify the resulting dependency graph:

```sh
pnpm install --frozen-lockfile
pnpm audit:docs
```

Run the quality checks applicable to the affected workspace components.

Never edit `pnpm-lock.yaml` manually.

### Dependency security

The project applies a seven-day minimum release age to registry dependencies and additional supply-chain security controls.

When introducing or updating dependencies:

- Review direct and transitive dependency changes.
- Verify that dependency licences are compatible with the project.
- Review the usage and distribution terms of downloaded model assets.
- Run the relevant integration tests and vulnerability audits.
- Preserve the configured dependency source, provenance and installation policies.

Do not weaken security controls to complete an installation or dependency update.

Urgent security fixes requiring an exception must follow the approval process described in [SECURITY.md](SECURITY.md).

### Updating GitHub Actions

GitHub Actions must be pinned to full commit SHAs.

After modifying an action reference, regenerate and verify `actions.lock` using the approved GitHub CLI extension.

Install the pinned extension if it is not already available:

```sh
gh extension install github/gh-actions-lock --pin v0.4.1
```

Regenerate and verify the lockfile:

```sh
gh actions-lock --no-narrow
gh actions-lock --verify --no-narrow
```

Review upstream repository identities, referenced commits and the resulting lockfile changes.

Commit the workflow changes and `actions.lock` together.

Never edit `actions.lock` manually or use `--accept-moved` in automation.

Changes to required CI jobs or permitted actions may also require maintainer updates to [repository security settings](.github/security-settings.md).

## 5. Submit a pull request

Open a pull request against `main` when your changes are ready for review.

Your pull request description should explain:

- **Problem.** What issue or requirement does this contribution address?
- **Changes.** What has been added, modified or removed?
- **Verification.** Which tests and quality checks demonstrate that the changes work?
- **Considerations.** Are there compatibility implications, dependency changes, limitations or remaining risks?

Keep contributions focused. Avoid combining unrelated refactoring, dependency upgrades and functionality changes in a single pull request.

### Commit conventions

Domain Kernel uses [Conventional Commits](https://www.conventionalcommits.org/).

Examples:

```text
feat: add document source validation
fix: preserve evidence references during review
docs: clarify model publication workflow
test: cover conflicting domain definitions
refactor: simplify discovery pipeline boundaries
```

Use the guided commit workflow:

```sh
pnpm commit
```

Alternatively, write a Conventional Commit message directly.

Commit message headers must not exceed 100 characters. Body and footer lines must also remain within 100 characters, except for URLs.

The configured commit-message hook validates commit messages using commitlint.

### Pull request checklist

Before requesting review, confirm that:

- [ ] The contribution addresses a clearly defined problem.
- [ ] The changes respect the SDK's architectural boundaries.
- [ ] Public API changes have been discussed where necessary.
- [ ] Relevant tests have been added or updated.
- [ ] Applicable quality checks pass.
- [ ] Documentation and examples reflect the changes.
- [ ] Dependency changes and engineering exceptions are justified.
- [ ] Dependency lockfiles remain consistent with their manifests.
- [ ] Generated distributions, coverage reports and SBOMs are excluded from the commit.

### Review and merge

All pull requests must pass the required CI checks and resolve outstanding review conversations before merging.

Additional review requirements apply to security-sensitive files.

Maintainers should follow the [repository security settings](.github/security-settings.md) for review requirements, repository administration and protected branches.

When merging through the GitHub CLI or API, maintainers must validate the intended commit title and body using:

```sh
pnpm exec commitlint --edit FILE
```

Use the validated commit message for the merge and verify the resulting CI run on `main`.

## 6. Security and releases

Report suspected vulnerabilities privately in accordance with the [security policy](SECURITY.md). Do not disclose unpatched vulnerabilities through public issues or pull requests.

Maintainers should follow the [release guide](docs/releasing.md) for version preparation, validation, tagging, artifact verification and publication.

## 7. Licence

Contributions to the SDK are licensed under the [Apache License 2.0](LICENSE).

Template-derived website code retains its separate [Tailwind Plus licence](apps/docs/LICENSE.md). Contributions to the documentation website must respect the applicable licensing terms.

Review the licensing terms of any third-party code, dependencies or assets introduced by your contribution.

---

Thank you for helping make Domain Kernel more reliable, accessible and useful.
