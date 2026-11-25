# Engineering conventions

Domain Kernel is an Apache-2.0 embeddable Python SDK, with a Python 3.13 minimum.
The package lives in `src/domain_kernel`; keep its PEP 561 `py.typed` marker.
Use implicit namespace packages for component and layer directories. Retain the
existing package-root `__init__.py` for the public SDK entry point.
Keep the core lightweight and optional adapter dependencies in named runtime extras.
SQLite is built in; PostgreSQL uses the `postgres` extra. Keep database imports
lazy so public and domain imports do not load persistence adapters.
Use typed discovery and reconciliation contracts. Keep filesystem, model-provider,
and adapter I/O at the boundaries.

## Agent skills

Use the applicable Domain Kernel skills for repository work. Matt Pocock's
skills can add a workflow. When their guidance conflicts with this file or a
Domain Kernel skill, follow the Domain Kernel guidance. Read supporting
references when the task needs them.

[Architecture](ARCHITECTURE.md) owns design and invariants. Inspected code
owns implementation status. Keep skill workflows within the user's assignment.
Commit, publish, or change GitHub state only with user authorization.

| Task | Skill |
|---|---|
| Design, implement or review responsibilities and dependency boundaries | [Coding Standards](.agents/skills/domain-kernel-coding-standards/SKILL.md) |
| Author or review Python contracts, services, adapters or examples | [Python Standards](.agents/skills/domain-kernel-python-standards/SKILL.md) |
| Implement behavior with TDD, choose test boundaries or assess verification | [Testing](.agents/skills/domain-kernel-testing/SKILL.md) |
| Write, edit, or review maintainer-facing Markdown on GitHub | [Maintainer Documentation](.agents/skills/domain-kernel-maintainer-docs/SKILL.md) |

### Supporting guidance

- Use [issue tracker guidance](docs/agents/issue-tracker.md) for issues, specs, tickets, and blockers.
- Use [triage labels](docs/agents/triage-labels.md) when reading or applying a triage state.
- Use [domain docs guidance](docs/agents/domain.md) when exploring or changing the domain model.

## Implementation and verification

Use explicit keyword arguments in Python documentation and examples. New SDK
parameters must be keyword-only, apart from implicit `self`/`cls` receivers.
Identifier value objects may accept their single value positionally or by keyword.
For positional-only Python helpers, use an equivalent construct rather than inventing
unsupported keyword arguments.

Use uv exclusively for Python dependencies. Use pnpm exclusively for website and
JavaScript tooling dependencies, with the committed pnpm lockfile and frozen
installs during checks. Node and pnpm are pinned in `mise.toml` and the private
workspace manifest. Turbo root tasks preserve the Python package layout.
Change Python dependencies with `uv add` or
`uv remove`, and include `pyproject.toml` and `uv.lock` together in commits.
Never hand-edit the lockfile or update it during checks or releases.
Keep the seven-day registry dependency cooldown in `tool.uv.exclude-newer` and
Dependabot. Do not bypass it with command-line, environment, package or index
overrides without a documented, reviewed security exception; see `SECURITY.md`.
Keep GitHub Actions pinned to full commit SHAs. After changing action references,
regenerate `.github/workflows/actions.lock` with `gh actions-lock --no-narrow`
and verify it with `gh actions-lock --verify --no-narrow`. Never hand-edit that
lockfile. Changes to repository protection definitions require applying them to
GitHub as described in `.github/security-settings.md`.

Choose checks for the area you changed. See [CONTRIBUTING.md](CONTRIBUTING.md#2-run-the-quality-checks)
for the full contribution checks.

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --group notebook --extra ontology --extra s3 --extra sharepoint --extra documents basedpyright
uv run --locked pytest -m "not integration"
uv run --locked pre-commit run --all-files
uv run --locked pytest --cov --cov-report=term-missing
uv build --no-sources
```

Ruff is the sole Python linter and formatter. ESLint, TypeScript and scoped Prettier
checks own website code and JavaScript tooling. Keep pre-commit as the single hook
manager; Commitizen and commitlint own Conventional Commit creation and validation.
BasedPyright checks `src/`, `tests/` and `development/`
with all diagnostics; annotate public APIs and test signatures explicitly.
Fix diagnostics at their cause. Any necessary exception must be narrow and
documented; do not add `Any`, casts, baselines, or blanket suppressions to pass.
Add meaningful tests under `tests/unit`; put slow or optional-adapter tests under
`tests/integration` and mark them `integration` so hooks remain fast.
CI's full suite collects both. If an integration test needs an extra, install
that extra explicitly in CI; do not make it a core dependency.

Keep generated distributions, coverage reports, and SBOMs out of Git.

Website development and manual Pages publication follow `docs/documentation.md`.
Use `pnpm check`, or its `check:sdk`, `check:notebook` and `check:docs` subsets.
Python setup is a shared prerequisite; parallel tasks must not resynchronize the
environment. Keep remote Turbo caching disabled and security/release checks uncached.
Never publish documentation on ordinary pushes, PRs, schedules or SDK tags.
Keep generated reference/site assets outside Git and Python distributions.
The notebook remains canonical and simulated results must remain visibly labelled.
