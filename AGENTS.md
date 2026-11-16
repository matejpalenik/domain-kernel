# Engineering conventions

Domain Kernel is an Apache-2.0 embeddable Python SDK, with a Python 3.13 minimum.
The package lives in `src/domain_kernel`; keep its PEP 561 `py.typed` marker.
Use implicit namespace packages for component and layer directories. Retain the
existing package-root `__init__.py` for the public SDK entry point.
Keep the core lightweight and adapter dependencies in named runtime extras.
Future discovery and reconciliation code should depend on explicit typed contracts;
keep filesystem, model-provider, and adapter I/O at the boundaries.

Use explicit keyword arguments in Python documentation and examples. New SDK
parameters must be keyword-only, apart from implicit `self`/`cls` receivers.
Identifier value objects may accept their single value positionally or by keyword.
For positional-only Python helpers, use an equivalent construct rather than inventing
unsupported keyword arguments.

Use uv exclusively for Python dependencies. Change dependencies with `uv add` or
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

Development commands:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked pytest -m "not integration"
uv run --locked pre-commit run --all-files
uv run --locked pytest --cov --cov-report=term-missing
uv build --no-sources
```

Ruff is the sole linter and formatter. BasedPyright checks `src/` and `tests/`
with all diagnostics; annotate public APIs and test signatures explicitly.
Fix diagnostics at their cause. Any necessary exception must be narrow and
documented; do not add `Any`, casts, baselines, or blanket suppressions to pass.
Add meaningful tests under `tests/unit`; put slow or optional-adapter tests under
`tests/integration` and mark them `integration` so hooks remain fast.
CI's full suite collects both. If an integration test needs an extra, install
that extra explicitly in CI; do not make it a core dependency.

Keep generated distributions, coverage reports, and SBOMs out of Git.
Preserve existing functionality; this infrastructure baseline does not implement
the planned business architecture.
