---
name: domain-kernel-coding-standards
description: "Design, implement or review Domain Kernel responsibilities, domain behavior and dependency boundaries. Use for architectural or coding decisions, including examples. Ordinary source tracing and editorial-only changes do not require this skill."
---

# Domain Kernel Coding Standards

Apply these conventions to new code and the responsibilities being changed.
Migrate existing code through deliberate refactors within its owning slice.
Preserve public contracts and durable behavior. Loading this skill does not
authorize delivery automation, commits or unrelated refactoring.

## Establish the owner and contract

Read the relevant [architecture](../../../docs/architecture/components-and-ownership.md#internal-architecture)
for intended behavior. Inspect the owning Python contracts and tests before changing
existing behavior. Resolve material contradictions before implementing dependent
behavior. Illustrative examples do not define new public APIs.

Choose the owning slice and layer before adding a class. The SDK's `api/` layer
exposes Python interfaces. Domain logic uses the standard library and does not
import API, application or infrastructure modules, even for type checking.
Application ports describe needed capabilities; infrastructure implements them.
Keep composition and concrete adapter selection at the SDK boundary.

## Put behavior with its meaning

- Put business invariants and permitted transitions on their domain owners.
  Editable entities change in place through named, synchronous methods and expose
  read-only properties. Keep aggregate children under their aggregate's control.
  Validate the full proposed change before mutating state.
- Use a focused domain policy for a rule spanning captured values from several
  owners. Give policies values and keep I/O, clocks and identity generation at
  the boundaries.
- Keep value objects and returned snapshots immutable, including definitions,
  decisions and publications. Reject duplicate names and preserve the agreed
  history and reservation rules. Keep the database's uniqueness, scope and
  compare-and-swap checks as additional integrity defenses.
- Keep the SDK's descriptive business processes separate from executable application
  workflows. Host authentication, operational records and downstream policy execution
  do not become SDK responsibilities.

## Keep orchestration explicit

Give each application service one business capability. Group related actions while
they share collaborators and orchestration. Split them when their dependencies or
reasons to change diverge.

Define a business-named protocol for every application service. Callers depend on
that protocol and composition chooses the implementation. Inject specific repository,
transaction and external-provider protocols directly. Compose operation-local
persistence collaborators over one session and inject a narrow transaction manager
as described in [state and persistence](../../../docs/architecture/persistence-and-reliability.md#state-and-persistence).

Make the write sequence visible in the service method. Show the transaction boundary,
load the required state, call the domain method and save its effects. Keep audit
writes and retry decisions visible when their order defines the outcome. Delegate
record construction, persistence mapping and resource lifetime to their owners.
Keep network and inference work outside database transactions.

Preserve scope, actor, inspected revision, retry intent and failure semantics when
simplifying a workflow. Use specific repositories and capabilities. Keep repository
registries, SQLAlchemy sessions, generic CRUD bases and command buses out of service
dependencies. Introduce additional interfaces where ownership or substitution calls
for them.

## Explain and verify the change

Use the [Python skill](../domain-kernel-python-standards/SKILL.md) for Python structure
and signatures. Use the [Testing skill](../domain-kernel-testing/SKILL.md) for TDD,
test design and verification evidence. Website work retains its own guidance and tools.

Document purpose, observable results, meaningful failures and resource ownership
when they cannot be inferred from the names and types. Use realistic values and
complete imports in examples. Label planned code and simulated results.

Check that the change preserves public contracts and that tests demonstrate behavior
at the right boundary. Follow [AGENTS.md](../../../AGENTS.md) for maintained commands
and security controls. Report what actually ran and what remains unverified.
