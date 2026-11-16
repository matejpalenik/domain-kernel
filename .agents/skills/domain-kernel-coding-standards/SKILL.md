---
name: domain-kernel-coding-standards
description: "Design, implement or review Domain Kernel responsibilities, domain behavior and dependency boundaries. Use for architectural or coding decisions, including examples. Ordinary source tracing and editorial-only changes do not require this skill."
---

# Domain Kernel Coding Standards

Apply these conventions to the authorized change. Keep work feature-by-feature and
proportionate; loading a skill does not authorize delivery automation, commits or
unrelated refactoring.

## Establish the owner and contract

Read the relevant [architecture](../../../ARCHITECTURE.md#internal-architecture),
[interface](../../../INTERFACES.md) and [roadmap issue](../../../ROADMAP.md).
The guides describe intended behavior; inspected code establishes what exists.
Resolve a material contradiction before implementing dependent behavior. Do not
turn an illustrative example into a new public API or scaffold the entire roadmap.

Choose the owning slice and layer before adding a class. The SDK's `api/` layer is
a Python interface, not a web server. Domain logic uses the standard library and
does not import API, application or infrastructure modules, even for type checking.
Application ports describe needed capabilities; infrastructure implements them.
Keep composition and concrete adapter selection at the SDK boundary.

## Put behavior with its meaning

- Put value invariants and permitted state transitions on their domain owners.
  Use a pure domain policy for a rule spanning captured values from several owners.
  Policies receive values, not repositories, sessions or provider clients.
- Keep aggregate children controlled by their aggregate and validate a proposed
  change before mutating anything. Reject duplicate names and preserve the agreed
  history/reservation rules; never invent suffixes to hide a collision.
- Keep immutable definitions, decisions and publications immutable. A valid domain
  value need not have mutation methods. Do not create an aggregate for every row.
- Let application services load facts, invoke domain behavior and persist its
  effects. Keep database uniqueness, scope predicates and compare-and-swap guards
  in adapters as additional integrity defenses, not replacements for domain rules.
- Keep the SDK's descriptive business processes separate from executable application
  workflows. Host authentication, operational records and downstream policy execution
  do not become SDK responsibilities.

## Keep orchestration explicit

Inject specific application-facing protocols directly into services. Compose
operation-local persistence collaborators over one shared session and transaction;
do not pass a broad repository registry or SQLAlchemy session into business code.
Use a narrow transaction manager for completion, as described in
[state and persistence](../../../ARCHITECTURE.md#state-and-persistence).

Retain the workflow's scope, actor, inspected revision, retry intent and failure
semantics. A shorter method is not an improvement if it loses those safeguards.
Distinguish observation, domain decisions, representation conversion, persistence
and resource lifetime. Keep network/inference work outside database transactions.

Use abstractions for meaningful boundaries and substitution, not hypothetical reuse.
Prefer specific repositories and capabilities over generic CRUD bases, command buses
or service locators. Do not require an interface for every pure value or helper.

## Explain and verify the change

Use the [Python skill](../domain-kernel-python-standards/SKILL.md) for authored Python
and the [Testing skill](../domain-kernel-testing/SKILL.md) for behavior implementation,
test design and verification evidence. Testing is the single owner of the TDD sequence.
Website work retains its own directory guidance and tools.

Explain purpose, observable results, meaningful failures and resource ownership.
Use realistic values and complete imports in examples; label planned code and
simulated results honestly. Put each rule in one authoritative place and link to it.
Document only details a reader cannot reliably infer from the names and types.

Check that the change preserves public contracts and that tests demonstrate behavior
at the right boundary. Follow [AGENTS.md](../../../AGENTS.md) for maintained commands
and security controls. Report what actually ran and what remains unverified.
