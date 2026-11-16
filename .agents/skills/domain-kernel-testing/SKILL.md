---
name: domain-kernel-testing
description: "Implement Domain Kernel behavior with TDD, choose unit and integration boundaries, isolate fixtures and assess verification evidence. Use for behavior changes, bug fixes, test design and notebook acceptance. Editorial-only changes need proportional document checks, not new application tests."
---

# Domain Kernel Testing

Test the behavior and state guarantee being changed. Use the owning roadmap issue
and [interface contract](../../../INTERFACES.md) to identify the observable result,
failure boundary and resources needed. [Coding Standards](../domain-kernel-coding-standards/SKILL.md)
owns responsibility boundaries; [Python Standards](../domain-kernel-python-standards/SKILL.md)
owns Python declarations and protocol doubles. This skill alone owns the TDD sequence.

## Behavioral TDD

For new behavior and bug fixes:

1. Establish only the public symbols and signatures needed to import and execute
   the test. Do not implement the behavior while creating this minimal seam.
2. Write the focused behavioral test and run it. Require failure for the intended
   behavior, not an import, syntax, fixture or collection error. Repair setup errors
   before treating the result as the red step.
3. Implement the smallest correct behavior. Run the focused test and relevant suite.
4. Refactor while tests remain green, then complete the required repository checks.

Do not invent tests for spelling changes or low-impact editorial work. Preserve
meaningful import-boundary and packaging tests: keeping domain code inward-facing
and public imports free of adapters are SDK guarantees. Avoid tests that merely
enforce filenames, class counts or implementation wording.

## Match evidence to the boundary

| Claim | Appropriate evidence |
|---|---|
| Domain invariant or transition | Real domain values, no database or service setup; rejection leaves inputs unchanged |
| Application orchestration | Real domain behavior and narrow protocol fakes, including failure and replay cases |
| Commit/rollback, locking, CAS, constraints or cleanup | Real SQLite/PostgreSQL adapter with isolated resources |
| Parser, inference or remote provider behavior | The actual selected adapter/provider, with explicit optional provisioning |
| Notebook teaching and preview controls | Canonical paired notebook checks and isolated experiments; simulated outputs remain labelled |

Read [testing examples](references/testing-examples.md) when selecting assertions,
writing fakes or designing persistence acceptance. Assert actual results and effects,
including absence of partial mutation on rejection. Use an independent expected
result rather than computing it with the production transformation under test.
Assert ordering only where it is part of the guarantee, such as replay before stale
revision rejection. Avoid a complete transcript of harmless implementation calls.

## Isolate resources and report limits

Use temporary files/databases and operation-local sessions; never point tests at a
developer's workspace database or live credentials. Teardown must work after setup,
assertion or cancellation failures. Do not silently fall back from PostgreSQL to
SQLite or from a real adapter to a mock. Dispose only resources the test owns.

Keep fast pure tests under `tests/unit`; mark slow or optional-adapter tests
`integration`. Use the existing `notebook` marker and notebook commands for the
preview. Explicitly install required extras in the owning CI job when those adapters
are implemented. No new test runner or delivery coordinator is needed.

Follow [AGENTS.md](../../../AGENTS.md) and [CONTRIBUTING.md](../../../CONTRIBUTING.md)
for maintained commands. Distinguish passed, failed, skipped, cached and unavailable
checks, and say whether a fixture or real integration ran. A timeout test does not
prove cancellation of underlying work; a mocked transaction does not prove rollback.

Replace only the notebook mocks owned by the implemented feature, record real
acceptance evidence in its coverage ledger, and preserve the connected narrative.
Never mark a roadmap issue complete because previews run, snippets parse or a skill
validator passes. Keep manual acceptance in the existing journey rather than creating
a second system of qualification issues.
