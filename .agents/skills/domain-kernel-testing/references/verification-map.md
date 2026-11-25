# Verification map

Read this when planning checks or reporting evidence for a changed behavior.
Start from the owning contract and follow **claim → real entry point → check →
evidence and limits**. Match the check to the claim and use the narrowest
existing command that reaches the affected boundary.

| Claim | Real entry point | Check | Evidence and limits |
|---|---|---|---|
| Domain transition or invariant | Entity method or domain policy | Focused `tests/unit` case with real domain values | Assert the result and rejection without partial mutation. |
| Service orchestration, failure or replay | Application service protocol | Focused test with real values and narrow protocol doubles | Assert outcome and effects. Ordering matters when it changes the outcome. |
| Commit, rollback, locking, compare-and-swap or cleanup | Public SDK operation or owning persistence contract | `tests/integration` with a temporary file-backed SQLite database or disposable PostgreSQL | Reopen through a fresh client or session and inspect durable state. Report evidence for each backend run. |
| Parser, inference or remote adapter behavior | Public SDK operation using the selected adapter | Focused integration test with explicitly provisioned adapter and controlled inputs | Identify the actual adapter, service or fixture. Scripted responses exercise handling of those inputs. |
| Complete SDK consumer journey | Public Python API or [recruitment quickstart](../../../../examples/recruitment_quickstart.py) | Run the example or public integration test with temporary state | Inspect returned values, reopened state or exported artifacts. The recruitment example transfers releases to a separate consumer process. |
| Canonical Jupyter journey | [Tour notebook](../../../../examples/notebooks/domain-kernel-tour.ipynb) | Execute the notebook in a fresh kernel with the existing harness | Inspect executed cell results and the reopened release. Report synthetic input, scripted inference and kernel restart coverage. |
| Installed wheel or source distribution | Normal import in a fresh environment | Follow the [CI build and package matrix](../../../../.github/workflows/ci.yml) and [package checks](../../../../development/package_checks.py) | Record artifact, Python version and extras. Check typed imports and adapter loading in the installed environment. |
| Website or notebook interaction | Running docs preview or Jupyter frontend | `pnpm check:docs` for site behavior and the [Jupyter Playwright config](../../../../apps/docs/playwright.notebook.config.ts) for Notebook or JupyterLab interaction | Inspect the affected flow and visible result. A saved walkthrough establishes reading behavior. A live frontend run establishes interaction. |
| Safety through difficult orderings | Bounded model plus public SDK operation | [Formal verification procedure](formal-verification.md) | Report assumptions, bounds, the broken variant and concrete replay. |

Follow [package commands](../../../../package.json), the
[documentation guide](../../../../docs/documentation.md) and
[contribution guide](../../../../CONTRIBUTING.md) for setup. Reuse `pnpm check:sdk`,
`pnpm check:notebook` and `pnpm check:docs` for their owning surfaces. Provision the
locked Python environment once and select the extras that the scenario actually uses.
Coordinate preparation before parallel checks and use focused `--no-sync` commands
for prepared environments. Confirm imports use the checkout or installed artifact
under review. Keep slow or adapter checks under the existing integration and
notebook markers.

## Execute the canonical notebook as a consumer

1. Locate the affected cells and their expected results in the
   [tour coverage ledger](../../../../examples/notebooks/coverage.json). Select
   a public integration case that exercises the same contract at a narrower boundary.
2. After the locked notebook tooling and documents extra are prepared, run the
   existing [offline execution test](../../../../tests/integration/test_notebook_preview.py)
   from the repository root. It invokes a real Jupyter kernel and executes the
   canonical notebook with test-owned PDF and provider inputs in a temporary workspace.

   ```sh
   uv run --locked --no-sync --offline pytest -q \
     'tests/integration/test_notebook_preview.py::test_tour_executes_offline_and_preserves_model_after_kernel_restart[valid]'
   ```

   The harness checks cell results against the ledger, reopens the release after a
   clean kernel restart and verifies zero new provider attempts. It also opens the
   transferred bundle in a separate consumer process. Use the relevant additional
   notebook case when the changed claim concerns error handling or UI interaction.
3. Record the visible result, pertinent durable effect, fixture or live input mode,
   and which backend or frontend ran. Pairing and saved-output validation count as
   document checks. A fixture journey exercises the real SDK with controlled external
   inputs. Live publisher resources or provider calls need their own authorized run
   and isolated workspace using the [notebook run guide](../../../../examples/notebooks/README.md#run-from-a-checkout).
   Keep output regeneration for changes that require updating the canonical artifacts.

## Report and maintain the evidence

Record each claim, the tested revision or working diff, exact command, fixture or
adapter, observed result and artifact when one exists. State any missing evidence
and why it matters to that claim. Cite the existing coverage ledger for notebook
acceptance. Keep the map linked to maintained entry points, and update its row
when the corresponding command, journey or expected behavior changes.
