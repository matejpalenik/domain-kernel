# Contributing

Thank you for your interest in contributing to Domain Kernel!

We welcome contributions that improve the SDK's functionality, reliability, documentation, and developer experience.

This guide explains how to set up your development environment, follow the project's engineering standards, run tests, and submit changes.

**Before contributing**, you may find these resources useful:

| Resource | Description |
|---|---|
| [README.md](README.md#quickstart) | Introduction and SDK quickstart |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture and component boundaries |
| [INTERFACES.md](INTERFACES.md) | Public interfaces and API contracts |
| [AGENTS.md](AGENTS.md) | Repository engineering conventions |

> [!NOTE]
> Domain Kernel is currently in pre-alpha development. Some documented capabilities are planned rather than implemented. Please distinguish between existing functionality and proposed interfaces when contributing code or documentation.

## 1. Set Up Your Development Environment

### Prerequisites

| Tool | Requirement |
|---|---|
| Python | 3.13 or newer |
| [uv](https://docs.astral.sh/uv/) | 0.13.7 or newer |
| Git | For version control and contributions |
| [mise](https://mise.jdx.dev/) | Optional, for managing development tools |

CI uses Python 3.13 and 3.14 with uv 0.13.7.

The repository provides `.python-version` to select Python 3.13 and an optional `mise.toml` that pins uv to the CI version.

If you're using mise, run `mise install` before continuing.

### Clone and Install

Clone the repository and install the development dependencies:

```sh
git clone https://github.com/matejpalenik/domain-kernel.git
cd domain-kernel

uv sync --locked
```

Enable the pre-commit hooks:

```sh
uv run --locked pre-commit install
```

Your environment now includes the core SDK and the development tools required for linting, formatting, type checking, and testing.

Optional adapter dependencies are installed separately when needed.

### Create a Feature Branch

Create a branch for your changes using the `feat/` prefix:

```sh
git switch -c feat/my-contribution
```

All changes to `main` must go through a pull request and pass the required CI checks.

## 2. Run the Quality Checks

Domain Kernel uses strict, automated quality checks to maintain a consistent and reliable codebase.

**Before submitting a pull request, run:**

```sh
uv run --locked pre-commit run --all-files
```

This runs the project's standard checks, including:

- **Ruff:** Python linting and formatting verification.
- **BasedPyright:** Strict static type checking.
- **Pytest:** Fast unit tests.
- **Repository hygiene:** Whitespace, end-of-file, and other consistency checks.

Some hygiene hooks automatically fix files. Review any changes before committing. Ruff formatting hooks only verify formatting and do not modify files.

### Individual Checks

You can also run checks independently while developing:

| Command | Purpose |
|---|---|
| `uv lock --check` | Verify the dependency lockfile |
| `uv run --locked ruff check .` | Run Python linting |
| `uv run --locked ruff format --check .` | Check Python formatting |
| `uv run --locked ruff format .` | Automatically format Python files |
| `uv run --locked --group notebook basedpyright` | Run strict static type checking, including notebook tests |
| `uv run --locked pytest -m "not integration"` | Run unit tests |
| `uv run --locked pytest --cov --cov-report=term-missing` | Run the full test suite with coverage |
| `uv audit --locked` | Audit locked dependencies for known vulnerabilities |

The dependency audit includes optional extras and development dependency groups and requires network access.

All checks use the committed `uv.lock` and must not modify dependency resolution.

### Python Compatibility

CI tests against Python 3.13 and 3.14.

When changing Python compatibility or version-sensitive behaviour, run the relevant checks against both versions:

```sh
UV_PYTHON=3.13 uv run --locked pytest
UV_PYTHON=3.14 uv run --locked pytest
```

If you export `UV_PYTHON` in your shell, restore the default environment afterwards:

```sh
unset UV_PYTHON
uv sync --locked
```

CI also performs reproducible builds, isolated wheel installation, SBOM validation, and GitHub Actions integrity verification.

For the complete release verification process, see the [Release Guide](docs/releasing.md).

## 3. Engineering Standards

Domain Kernel follows strict engineering conventions to keep the SDK maintainable, predictable, and suitable for integration into enterprise applications.

### Architecture and Dependencies

- **Keep the core lightweight.** Optional integrations and adapters should not introduce unnecessary dependencies into the core SDK.
- **Respect component boundaries.** Keep filesystem access, external providers, and adapter I/O at the appropriate boundaries.
- **Use explicit contracts.** Components should communicate through clearly defined, strongly typed interfaces.
- **Preserve the public API.** Maintain package-root exports and the `py.typed` marker. Component and layer directories use implicit namespace packages.

For architectural decisions and interface definitions, consult [ARCHITECTURE.md](ARCHITECTURE.md) and [INTERFACES.md](INTERFACES.md).

### Python Conventions

Domain Kernel uses **Ruff as its sole linter and formatter** and **BasedPyright for strict type checking**.

The project enforces:

- All stable Ruff rules, with preview rules disabled.
- Google-style docstrings and the documented exceptions in `pyproject.toml`.
- BasedPyright's `all` diagnostic mode for both `src/` and `tests/`.
- Explicit type annotations for public APIs and test signatures.
- Keyword-only parameters for new SDK APIs, except identifier value objects, which may accept their single value positionally or by keyword.
- Explicit keyword arguments in examples when supported by the callable.

**Resolve linting and typing issues at their source.** Avoid introducing `Any`, unnecessary casts, broad suppressions, or diagnostic baselines simply to make checks pass.

Any necessary exception must be narrowly scoped and documented.

### Tests

Include meaningful tests for new functionality and behaviour changes.

| Test type | Location | Requirements |
|---|---|---|
| Unit tests | `tests/unit/` | Fast, deterministic tests without external services |
| Integration tests | `tests/integration/` | Mark with `integration`; may require optional adapters or external dependencies |

The current test suite covers foundational contracts, identifiers, errors, and package metadata.

Coverage is reported without enforcing a minimum threshold.

To work on optional integrations, install the corresponding adapter dependencies explicitly. For example, ontology integration tests can be run with:

```sh
uv sync --locked --extra ontology
uv run --locked --extra ontology pytest -m integration
```

> [!NOTE]
> No integration tests are implemented yet. The command above becomes useful once marked integration tests are introduced.

When adding integration tests, ensure their dependencies are also installed in the relevant CI jobs.

## 4. Managing Dependencies

Domain Kernel uses **uv exclusively for Python dependency management**.

Direct dependencies are declared in `pyproject.toml`, with the resolved dependency graph committed in `uv.lock`.

### Add or Remove Dependencies

Use uv to modify dependencies:

```sh
uv add PACKAGE
uv remove PACKAGE
```

For optional adapter dependencies, use the appropriate named extra:

```sh
uv add --optional EXTRA PACKAGE
```

Always commit changes to `pyproject.toml` and `uv.lock` together.

**Never edit `uv.lock` manually.**

### Update Existing Dependencies

For an intentional dependency upgrade:

```sh
uv lock --upgrade-package PACKAGE
uv sync --locked
uv run --locked pre-commit run --all-files
uv audit --locked
```

Review the complete lockfile diff, including transitive dependency changes.

When adding or upgrading optional adapters, also verify:

- Relevant integration tests continue to pass.
- Dependency licences are compatible with the project.
- Separately downloaded model assets have acceptable usage and distribution terms.

### Dependency Security

The project enforces a **seven-day minimum artifact age** for registry dependencies, covering runtime, optional, development, and build dependencies.

Dependabot checks uv and GitHub Actions dependencies weekly and follows the same delay.

This policy helps reduce exposure to newly published, potentially compromised packages.

See [SECURITY.md](SECURITY.md#dependency-update-policy) for the complete policy and procedures for urgent security fixes.

### Updating GitHub Actions

GitHub Actions must be pinned to full commit SHAs.

After updating an action reference, regenerate and verify `actions.lock` using the pinned GitHub CLI extension:

```sh
gh extension install github/gh-actions-lock --pin v0.4.1

gh actions-lock --no-narrow
gh actions-lock --verify --no-narrow
```

The extension installation is only necessary if it is not already available.

Commit the updated workflow and `actions.lock` together.

**Security requirements:**

- Preserve full commit SHA references using `--no-narrow`.
- Never edit `actions.lock` manually.
- Do not use `--accept-moved` in automation.
- Review changes to both upstream repository identities and referenced commits.

Adding an action or changing a required CI job may also require updating GitHub repository settings.

See [Repository Security Settings](.github/security-settings.md) for instructions.

## 5. Submit a Pull Request

Once your changes are ready, open a pull request against `main`.

### Pull Request Checklist

Before requesting review, make sure that:

- [ ] Changes are focused and preserve existing functionality.
- [ ] Relevant tests have been added or updated.
- [ ] All local quality checks pass.
- [ ] Documentation and examples reflect the changes.
- [ ] New dependencies and any linting or typing exceptions are explained.
- [ ] Generated artifacts are excluded from the commit.

Your pull request description should explain **what problem you're solving, what changed, and how you verified it**.

Use conventional commit messages, for example:

```text
feat: add domain relationship validation
fix: validate model identifiers
docs: clarify development setup
test: cover conflicting model definitions
```

### Review and Merge

All pull requests must pass the required CI checks, and review conversations must be resolved before merging.

Security-sensitive files have designated code owners. The sole-maintainer review exception is documented in [Repository Security Settings](.github/security-settings.md).

Do not commit generated distributions, coverage reports, or SBOMs.

## 6. Security and Releases

**Reporting vulnerabilities:** Please report security issues privately using the process described in [SECURITY.md](SECURITY.md). Do not disclose suspected vulnerabilities in public issues.

**Publishing releases:** Maintainers should follow the [Release Guide](docs/releasing.md) for version preparation, validation, tagging, and publication.

## License

By contributing to Domain Kernel, you agree that your contributions will be provided under the repository's [Apache License 2.0](LICENSE).
