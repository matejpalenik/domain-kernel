# Document discovery benchmark

This repository maintains its own evaluation of document discovery. The European
Union procurement notices are source documents for our corpus and rubric, not
an external scoring suite.

## Replay the v23 archive

From the repository root, with the private bundle described in the
[v23 scorecard](../docs/evidence/discovery-v23.md):

```sh
pnpm python:prepare
pnpm benchmark
```

The replay verifies the saved inputs and scores for the original run and the
separate review-example fix rerun. It also runs SDK checks against captured
responses. The replay uses no network or provider calls.

## EU procurement

After preparing the environment as shown above, list the commands:

```sh
uv run --locked --no-sync python -m benchmarks.procurement --help
uv run --locked --no-sync python -m benchmarks.procurement validate --inputs-only
```

The workspace defaults to `local/benchmarks/procurement`. Use `--root` on a
subcommand to select a different workspace.

| Subcommand | Purpose |
|---|---|
| `prepare --root PATH` | Select development and locked packets from local candidate captures and write a draft key. Use a new workspace to protect frozen captures. |
| `validate --inputs-only` | Verify local source captures and the pinned reference ontology. Omit `--inputs-only` to also require and validate an independently reviewed key. |
| `submit --output PATH --submission FILE` | Import an existing submission for scoring without running discovery. |
| `score --output PATH --judgments FILE` | Score a saved campaign against its frozen manifests and reviewer judgments. |

These commands work offline. `run` and `smoke` are separate live commands and
can incur provider charges. The live runner uses `Model.discover()` and can
collect a matched direct-provider control. The local draft and late reference
comparisons share one discovery run.

Keep prepared originals, scoring keys and usage receipts outside source control.
See the [evaluation methodology](../docs/evidence/discovery-benchmark-methodology.md)
for independent review, holdout and reporting requirements.
