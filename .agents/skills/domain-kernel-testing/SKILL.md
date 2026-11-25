---
name: domain-kernel-testing
description: "Develop Domain Kernel behavior with TDD, verify SDK changes through the public API and Jupyter notebook, and select integration or formal checks for consequential guarantees."
---

# Domain Kernel Testing

Use the [architecture](../../../ARCHITECTURE.md) and owning Python contract to state
the observable claim, its failure boundary and what done means.
[Coding Standards](../domain-kernel-coding-standards/SKILL.md) owns responsibilities.
[Python Standards](../domain-kernel-python-standards/SKILL.md) owns Python
declarations and protocol doubles. This skill owns the TDD sequence and evidence.

## Behavioral TDD

For new behavior and bug fixes:

1. Establish only the public symbols and signatures needed to run the test.
2. Write the focused behavioral test and confirm it fails for the intended
   behavior. Repair import, collection or fixture errors before counting a red result.
3. Implement the smallest correct behavior. Run the focused test and relevant suite.
4. Refactor while tests stay green, then complete the checks for the changed claims.

Use proportional document checks for editorial changes. Preserve import-boundary
and packaging guarantees. Check structural rules in review or static checks.
Read [testing examples](references/testing-examples.md) when choosing assertions,
protocol doubles or persistence acceptance. Assert results and effects, including
prior state on rejection. Derive expected results independently of the code under
test. Assert ordering where the guarantee depends on it.

## Verify through the affected boundary

Use the [verification map](references/verification-map.md) to connect each claim to
its real entry point, check, evidence and limits. Use existing SDK, package,
notebook and browser checks.

For SDK changes covered by the canonical tour, pair a focused integration test
through the public Python API with fresh execution of the affected Jupyter
journey. Observe the visible result and persisted or exported effects.
Use the isolated offline notebook execution for repeatable evidence. Label
fixture inputs and scripted inference. Record acceptance in the existing coverage
ledger. Preserve the paired notebook files and connected narrative. For changes
outside the tour, use the affected public integration path or example.

For a consequential invariant with hard-to-exercise orderings, read
[formal verification](references/formal-verification.md). Pair a bounded TLA+/TLC
check with a concrete SDK regression and record their coverage separately.

Use temporary workspaces, disposable databases and operation-local sessions.
Clean up owned resources even on failure or cancellation. Report each tested adapter
and input mode. Name required checks that failed, were skipped, were cached or
were unavailable. This keeps an unavailable PostgreSQL check visible alongside a
SQLite pass. Credit acceptance only when the evidence reaches the claimed boundary.
Follow [AGENTS.md](../../../AGENTS.md) and
[CONTRIBUTING.md](../../../CONTRIBUTING.md) for commands and provisioning.

## Work within the trust ladder

Adapt [Lauren Tan's trust-before-the-loop practice](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/07-overnight.md#earn-the-trust-before-the-loop)
to a specific class of work. Accept the task's authorized scope as the limit on
autonomy. Evidence supports the user's decision to delegate further.

| Level | What the agent does |
|---|---|
| Observed | Agree on the acceptance criteria and walk one representative change with the requester. Drive the real entry point and show what success and failure look like. |
| Self-verifying | Complete a bounded change in the owning slice. Run the mapped checks and report the tested revision or working diff, commands, observations, artifacts and limits. |
| Independent and parallel | When parallel work is authorized, isolate each change and its runtime state. Have an independent reviewer rerun the checks that establish the higher-risk claims on the reviewed code. Bring each change back with its own evidence. |
| Bounded unattended | Use explicitly delegated tasks with a checkable finish condition and stopping conditions. Stop the unattended path when required evidence is unavailable, the acceptance criteria change, or the work would exceed its authorization. Preserve partial evidence for review. |

Use repeated successful runs and independent reruns to propose moving up a level.
Turn recurring failures into focused checks or clearer instructions. A green check
covers its stated claim and environment. Commit, publish, merge and deployment
permissions come from the task and repository policy.
