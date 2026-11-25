---
name: setup-pre-commit
description: Install or update Domain Kernel's existing pre-commit and commit-msg hooks with uv.
---

# Set up Git hooks

Use the [contributor setup guide](../../../CONTRIBUTING.md) to provision the
locked development environment. Install the two hooks from the repository root.

```sh
uv run --locked pre-commit install --hook-type pre-commit --hook-type commit-msg
```

[.pre-commit-config.yaml](../../../.pre-commit-config.yaml) owns what runs.
The pre-commit hook runs repository checks. The commit-msg hook uses commitlint.
For a hook change, update the owning configuration and verify the affected hook
with `uv run --locked pre-commit run`. Use the appropriate stage for commit
messages and the [full contribution checks](../../../CONTRIBUTING.md#2-run-the-quality-checks)
when a change affects the whole hook configuration.
