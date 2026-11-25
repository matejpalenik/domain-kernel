---
name: domain-kernel-python-standards
description: "Author or review Domain Kernel Python module layout, contracts, domain behavior, services, adapters, tests, docstrings and examples. Reading Python during an editorial task alone does not require this skill."
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
[internal architecture](../../../docs/architecture/components-and-ownership.md#internal-architecture) and
[state and persistence](../../../docs/architecture/persistence-and-reliability.md#state-and-persistence).

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

## Document Python contracts

Use PEP 257 layout with Google-style sections. Use triple double quotes and an
imperative summary ending in a period for functions and methods. Describe a
property's value with a noun phrase. Use one line when the summary covers the
contract beyond the signature. For multiline docstrings, leave a blank line
after the summary. [PEP 257](https://peps.python.org/pep-0257/)

Put shared guarantees, invariants and ownership on the class or protocol. A
method marked `@override` can rely on the inherited docstring. Document any
material refinements or side effects on the override. Give each public SDK
method its own caller-facing contract. Put operation-specific rules on the
owning method. Use `Attributes:` for public fields whose meaning needs
explanation and document constructor-specific argument rules on `__init__`.

- Use `Args:` when callers need to know constraints, units, scope, special values
  or relationships between parameters. List every caller-supplied parameter by
  its exact name and use annotations for types.
- Use `Returns:` to explain what a result means, including absence and pagination
  when relevant. Omit it when the summary suffices or when the method returns
  only `None`. Use `Yields:` to explain what a generator emits.
- Use `Raises:` for stable failures a caller can reasonably handle. Name each
  exception and when it occurs. Document required preconditions and name the
  validation error when the interface promises one.
- Use `Examples:` when a short call or sequence clarifies a contract, such as
  reusing a returned cursor. Use explicit keyword arguments in SDK examples.
  Put longer workflows in the SDK guide or notebook.

Use the existing Ruff checks for presence and formatting. Review summary mood
and contract completeness against the architecture, callers and supported
implementations. Check that a caller can supply valid arguments, interpret
the result and handle expected failures.

This `SourceRepository` excerpt illustrates a one-line lookup and a guarded
write. [Source repository port](../../../src/domain_kernel/sources/application/ports.py)

```python
class SourceRepository(Protocol, metaclass=ABCMeta):
    """Persist project sources, immutable revisions, and guarded operation results.

    Writes participate in the caller's transaction.
    """

    @abstractmethod
    async def find_by_name(self, *, project_id: ProjectId, name: str) -> Source | None:
        """Find a source by exact lookup name in the project, or return None."""

    @abstractmethod
    async def save(self, *, source: Source, expected_version: int | None) -> None:
        """Create a source or update it at the expected version.

        Args:
            source: Source state to persist, including the version to store.
            expected_version: Pass None to create a source. To update a source,
                pass the version read before preparing the change.

        Raises:
            SourceAlreadyExistsError: Creation finds the lookup name in use in the project.
            StaleStateError: The update finds no source at the expected version.
        """
```

## Test and document the actual claim

Use [Testing](../domain-kernel-testing/SKILL.md) for TDD and evidence boundaries.
Keep exception translation narrow, preserve causes and sanitize external diagnostics.
Preserve `model.info` and other loaded properties as I/O-free snapshots.

Follow [AGENTS.md](../../../AGENTS.md) for uv, checks and security controls. Use the
database dependencies and extras declared by the SDK. Label planned examples and
exercise real adapters when the claim depends on their behavior.
