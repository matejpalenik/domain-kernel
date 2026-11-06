# Contributing

Use Python 3.13 or newer and follow the [development workflow](README.md#development).
Keep changes focused, add tests for behavior changes, and include the commands
you ran in your pull request. Explain any new dependency, lint exception, or
typing exception. Public APIs require explicit type annotations.

Core dependencies must remain small; dependencies used only by adapters belong
in the appropriate optional extra. Use `uv add` / `uv remove` and commit the
resulting `uv.lock` with `pyproject.toml`. Review license compatibility and run
`uv audit --locked` after dependency updates. Do not add generated reports.

Contributions are provided under the repository's Apache-2.0 license.
