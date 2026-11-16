---
name: domain-kernel-python-standards
description: "Author or review Domain Kernel Python contracts, domain behavior, application services, persistence adapters, tests and code examples. Apply the SDK's typing, protocol and resource conventions. Reading Python during an editorial task alone does not require this skill."
---

# Domain Kernel Python Standards

Use [Coding Standards](../domain-kernel-coding-standards/SKILL.md) for responsibility
and dependency decisions. Inspect the relevant design contract and implemented
module before changing it. These standards do not migrate existing code implicitly.

## Preserve the SDK's Python contract

- Keep Python 3.13+, implicit component/layer namespace packages, the public root
  exports and `py.typed`. Internal code imports its defining modules without using
  the public root as an internal dependency hub. Consumer examples use public exports.
- Use keyword-only new SDK parameters and explicit keyword arguments in examples.
  Retain the identifier single-value exception and respect positional-only standard
  library APIs. Do not invent keyword arguments a dependency does not support.
- Keep nominal ID types distinct and preserve their opaque string representation.
  Separate generated identity, stable lookup name and display name. Introduce a
  value object when it protects meaning or invariants, not for every string.
- Use frozen, keyword-only dataclasses for domain records, with slots where useful
  and compatible. Use enums for closed vocabularies. Accept declared `Sequence`
  inputs, validate and freeze them; show lists in caller examples. Preserve tuples
  for immutable results/defaults and genuine fixed-position structures.
- Keep domain records stdlib-only. Configuration and boundary validation may use
  the existing Pydantic conventions; ORM mappings belong only in infrastructure.
- Preserve strict BasedPyright and Ruff. Fix typing causes without `Any`, casts,
  broad suppression or new baselines. Group related types when that improves clarity;
  do not require one public type per file or static classes for every pure function.

## Use protocols at real boundaries

Application services, repositories, transaction management and external adapters
depend on specific protocols. Declare required authored protocol methods with
`@abstractmethod`; explicitly inherit intended protocols and use `@override` on
implementations and fakes. Interface-guide ellipses describe signatures, not usable
default implementations. Do not force a pure domain policy to import an application
protocol; structural conformance preserves the dependency rule there. Do not require
runtime protocol checks unless the operation actually needs them.

Explicit inheritance is a repository authoring convention. Host-provided structural
implementations remain supported; do not turn this convention into a new public
requirement to inherit SDK base classes.

Read [domain and protocol examples](references/domain-and-protocols.md) when adding
domain transitions, values or capability boundaries. Keep domain behavior synchronous
and independent of I/O, clocks and identity generation by passing captured values.

## Keep services and persistence readable

For service/persistence work, read [services and persistence](references/services-and-persistence.md).
The governing contracts are [internal architecture](../../../ARCHITECTURE.md#internal-architecture)
and [state and persistence](../../../ARCHITECTURE.md#state-and-persistence).

Inject specific collaborators directly. The service coordinates a short transaction,
loads detached domain values, invokes their behavior and persists effects with audit
and retry outcomes. The composition boundary gives all persistence collaborators one
operation-local session. Repositories never commit. Keep source acquisition, parsing,
inference and waiting outside that transaction.

Await persistence reads and writes, including audit and idempotency. Factory methods
returning async context managers stay synchronous. Builders, loaded getters and pure
policies stay synchronous; do not add async merely for naming symmetry.

Use SQLAlchemy typed ORM mappings/expressions for SDK persistence and explicit
row-to-domain conversion. Keep session/engine cleanup at the resource boundary and
avoid lazy-loading I/O in returned values. A cancelled or failed commit may be
uncertain; follow durable recovery rather than reporting a false rollback/success.

## Test and document the actual claim

Use [Testing](../domain-kernel-testing/SKILL.md) for TDD and evidence boundaries.
Keep exception translation narrow, preserve causes and sanitize external diagnostics.
Docstrings explain non-obvious contracts, failures and ownership without repeating
signatures. Preserve `model.info` and other loaded properties as I/O-free snapshots.

Follow [AGENTS.md](../../../AGENTS.md) for uv, checks and security controls. SQLAlchemy
and aiosqlite remain future DK-003 dependencies until implementation; PostgreSQL is
optional. Do not install packages merely to make a planned documentation example look
implemented or silently replace a missing real adapter with a fake.
