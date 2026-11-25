---
name: domain-kernel-python-standards
description: "Author or review Domain Kernel Python module layout, contracts, domain behavior, services, adapters, tests and examples. Reading Python during an editorial task alone does not require this skill."
---

# Domain Kernel Python Standards

Use [Coding Standards](../domain-kernel-coding-standards/SKILL.md) for ownership,
dependency direction and refactor scope. Inspect the relevant design contract and
implemented module before changing it.

## Organize Python by named type and capability

- Give each production class, protocol, dataclass, enum and reusable type alias its
  own snake_case file, including private classes. Name the file after its type, such
  as `publication_service.py` or `clock.py`. Group related files by capability inside
  the existing slice and layer.
- Keep local constants, private aliases and tightly coupled private functions with
  their owner. Standalone functions also serve function-shaped entry points such as
  pytest fixtures and existing module-level SDK APIs. Test-local doubles can stay
  with their tests. Give shared test doubles their own files.
- Put reusable behavior on its domain owner. Use focused policy or utility classes
  for other reusable stateless behavior. Call static methods through the class,
  for example `TextUtilities.remove_whitespaces(text=raw_text)`.

## Preserve the SDK's Python contract

- Keep Python 3.13+, implicit component/layer namespace packages, the public root
  exports and `py.typed`. Internal code imports defining modules. Consumer examples
  use public exports.
- Use keyword-only new SDK parameters and explicit keyword arguments in examples.
  Retain the identifier single-value exception and respect positional-only
  dependency APIs.
- Keep nominal ID types distinct and preserve their opaque string representation.
  Separate generated identity, stable lookup name and display name. Introduce a
  value object when it protects meaning or invariants.
- Use frozen, keyword-only dataclasses for immutable domain values and snapshots,
  with slots where useful and compatible. Use enums for closed vocabularies. Accept
  declared `Sequence` inputs, validate and freeze them, and show lists in caller
  examples. Use tuples for immutable results/defaults and genuine fixed-position
  structures.
- Keep domain records stdlib-only. Configuration and boundary validation may use
  the existing Pydantic conventions. ORM mappings belong in infrastructure.
- Preserve strict BasedPyright and Ruff. Fix typing causes without `Any`, casts,
  broad suppression or new baselines.

## Express behavior with typed contracts

Name each service protocol for its capability, such as `RegisterRevision`, and
its implementation `RegisterRevisionService`. Use business-named methods. Declare
required authored protocol methods with `@abstractmethod`, explicitly inherit
implemented protocols, and use `@override` on implementations and fakes. Interface
guide ellipses describe signatures. Keep host-provided structural implementations
supported. A pure domain policy may satisfy an application protocol structurally
to preserve dependency direction. Use runtime protocol checks where behavior
requires them.

Give each application-layer business write a named, frozen, keyword-only command,
including writes with a single input. Preserve existing public and specified
cross-slice signatures by assembling commands behind those entry points. Simple
reads can take explicit keyword-only arguments. Return a typed result when the caller
needs one. Use `None` when successful completion is the outcome.

In-place entity transitions return `None` by default. Return a meaningful domain
result when the transition produces one. Keep fluent `return self` out of entity
transitions. Read [domain and protocol examples](references/domain-and-protocols.md)
when adding domain transitions, values or capability boundaries.

## Keep services and persistence readable

Read [services and persistence](references/services-and-persistence.md) for service
writes, adapter mapping or resource composition. The governing contracts are
[internal architecture](../../../ARCHITECTURE.md#internal-architecture) and
[state and persistence](../../../ARCHITECTURE.md#state-and-persistence).

Within the write transaction, load a detached entity. Capture its original version
for a compare-and-swap save and immutable before-state or a digest for audit as
required. Call the entity's synchronous transition and explicitly save the changed
entity. Await persistence reads and writes, including audit and idempotency.
All persistence collaborators in the operation share one session. Repositories
never commit. Keep source acquisition, parsing, inference and waiting outside the
transaction.

Factory methods returning async context managers, builders, loaded getters and pure
policies have synchronous call interfaces. Use typed SQLAlchemy ORM
mappings/expressions and explicit row-to-domain conversion. Keep cleanup at the
resource boundary and avoid lazy-loading I/O in returned values. Recover uncertain
commit outcomes using the original durable identity.

## Test and document the actual claim

Use [Testing](../domain-kernel-testing/SKILL.md) for TDD and evidence boundaries.
Keep exception translation narrow, preserve causes and sanitize external diagnostics.
Docstrings explain non-obvious contracts, failures and ownership. Preserve
`model.info` and other loaded properties as I/O-free snapshots.

Follow [AGENTS.md](../../../AGENTS.md) for uv, checks and security controls. Use the
database dependencies and extras declared by the SDK. Label planned examples and
exercise real adapters when the claim depends on their behavior.
