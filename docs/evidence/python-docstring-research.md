# Python docstring research

Domain Kernel already uses Google-style docstrings with Ruff's `google`
convention. The SDK targets Python 3.13 and later, annotates public APIs, and
uses keyword-only parameters for new SDK calls. The Python standards ask
docstrings to explain non-obvious contracts, failures and ownership. A
docstring review can ask what a caller or adapter author still needs to know
after reading the signature. [Engineering conventions](../../AGENTS.md),
[Python standards](../../.agents/skills/domain-kernel-python-standards/SKILL.md),
[Ruff configuration](../../pyproject.toml)

## What the sources ask for

**PEP 257** is Active and Informational. It describes how docstrings become
`__doc__` and gives high-level conventions while leaving markup open. It
suggests triple double quotes, an imperative one-line function summary
ending in a period, and a blank line between a multiline summary and its
details. It reserves one-liners for obvious cases and discourages restating
the signature. Where applicable, it calls for arguments, results, side
effects, exceptions and calling restrictions. It also distinguishes a
class's public interface from any additional interface for subclass authors.
[PEP 257](https://peps.python.org/pep-0257/)

**PEP 8** gives the standard library's Python coding conventions and gives
project-specific guides precedence in a conflict. Its docstring section
points to PEP 257 and calls for docstrings on public modules, functions,
classes and methods. Its rules leave the section format to the project.
[PEP 8 introduction](https://peps.python.org/pep-0008/#introduction),
[PEP 8 on docstrings](https://peps.python.org/pep-0008/#documentation-strings)

**Google's Python Style Guide** requires a docstring for public, nontrivial
or non-obvious functions. It allows imperative or descriptive summaries
with consistent usage within a file. The punctuated summary fits on one
line of at most 80 characters. Additional text follows a blank line. A
one-liner can suffice when the name and signature carry enough information.
The guide asks for observable behavior, including relevant mutation and
the effect of decorators.
[Google's docstring layout](https://google.github.io/styleguide/pyguide.html#docstrings),
[Google on functions and methods](https://google.github.io/styleguide/pyguide.html#function-docs)

| Section | What Google's guide asks for |
| --- | --- |
| `Args:` | List each parameter by name when using this section. Include type information when the signature lacks an annotation. [Google on arguments](https://google.github.io/styleguide/pyguide.html#doc-function-args) |
| `Returns:` and `Yields:` | Explain what the value means and supply type information missing from the annotation. A `None`-only return or a sufficient opening sentence can make `Returns:` unnecessary. For generators, describe the yielded values. [Google on results](https://google.github.io/styleguide/pyguide.html#doc-function-returns) |
| `Raises:` | List the exceptions relevant to the interface and explain when they occur. The guide excludes exceptions from violations of the documented API. [Google on exceptions](https://google.github.io/styleguide/pyguide.html#doc-function-raises) |

Google calls for annotations when adding or changing public APIs. Its class
guidance uses `Attributes:` for public attributes and gives properties their
own attribute-style descriptions. An explicit `@override` can rely on the
base method's docstring unless the implementation adds material behavior or
details. [Google on typed code](https://google.github.io/styleguide/pyguide.html#typed-code-decision),
[classes](https://google.github.io/styleguide/pyguide.html#class-docs),
[overrides](https://google.github.io/styleguide/pyguide.html#overridden-method-docs)

The Python typing specification defines protocol conformance through compatible
members and permits implicit implementations. Matching signatures leave room
for different behavior. Recording shared semantics on the protocol gives
callers and implementers a common contract. `@override` is a type-checker
signal for an inherited member. Tools such as `inspect.getdoc()` can find
inherited documentation in supported cases. That lookup follows the class
hierarchy, so a protocol docstring is available this way only through explicit
inheritance.
[Typing specification on protocols](https://typing.python.org/en/latest/spec/protocol.html),
[typing specification on `@override`](https://typing.python.org/en/latest/spec/class-compat.html#override),
[Python 3.13 `inspect.getdoc`](https://docs.python.org/3.13/library/inspect.html#inspect.getdoc)

## What a different format would change

- **numpydoc** uses underlined sections such as `Parameters` and `Returns`.
  It permits an omitted parameter type, but requires the type in `Returns`
  and `Yields`. It makes `Raises` optional and suggests using it for
  non-obvious or likely errors. A switch would change the source layout and
  could duplicate types that already appear in annotated signatures.
  [numpydoc format](https://numpydoc.readthedocs.io/en/latest/format.html#sections)
- **Sphinx** supports reStructuredText fields such as `:param:`, `:returns:`
  and `:raises:`. Its Napoleon extension reads both Google and NumPy
  docstrings, and autodoc can display annotation types from the signature.
  Domain Kernel's current reference reads root exports with Python's AST and
  displays each symbol's docstring as a plain paragraph. Changing how the
  reference presents sections or internal port methods would require changes
  to its reader or renderer.
  [Sphinx Python fields](https://www.sphinx-doc.org/en/master/usage/domains/python.html#info-field-lists),
  [Napoleon](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html),
  [autodoc type hints](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#confval-autodoc_typehints),
  [reference reader](../../development/docs.py),
  [reference component](../../apps/docs/src/components/SdkReference.tsx)

## What Ruff checks in this checkout

Ruff's `google` setting filters the selected `D` rules. Domain Kernel
selects `ALL`, applies its own ignores, and has preview mode off. Ruff
checks summary punctuation with `D415`. The Google convention excludes
`D401`, so requiring imperative summaries would be a project choice.
`D417` checks parameter coverage when an arguments section is present. Ruff's
preview checks for missing `Returns` and `Raises` sections inspect return
statements and explicitly raised exceptions respectively. They also exempt
abstract methods, where a protocol may need to spell out those promises.
[Ruff conventions](https://docs.astral.sh/ruff/settings/#lintpydocstyleconvention),
[`D401`](https://docs.astral.sh/ruff/rules/non-imperative-mood/),
[`D415`](https://docs.astral.sh/ruff/rules/missing-terminal-punctuation/),
[`D417`](https://docs.astral.sh/ruff/rules/undocumented-param/),
[`DOC201`](https://docs.astral.sh/ruff/rules/docstring-missing-returns/),
[`DOC501`](https://docs.astral.sh/ruff/rules/docstring-missing-exception/),
[repository settings](../../pyproject.toml)

The checkout's Ruff 0.17.4 passes both the source port module and its
SQLite implementation. A `D417` check of two small functions sent through
stdin accepted a one-line docstring and flagged only the missing parameter
in the other function's partial `Args:` section. A `D102` probe flagged an
undocumented public method and exempted the same method when explicitly
decorated with `typing.override`. The design, callers and implementations
provide the evidence for whether a docstring states the relevant promises.
[`D102`](https://docs.astral.sh/ruff/rules/undocumented-public-method/)

## What a reader needs from `SourceRepository`

`SourceRepository` is an internal application port. Its `get`,
`find_by_name`, `save` and `list` methods all have one-line docstrings.
`SQLiteSources` explicitly implements the protocol and has `@override`
with no docstrings on those four methods. The table records the inspected
SQLite behavior and service call sites. Treat each item as a candidate
shared promise until the design and supported implementations establish
its scope. [Source port](../../src/domain_kernel/sources/application/ports.py),
[SQLite implementation](../../src/domain_kernel/sources/infrastructure/sqlite_sources.py),
[calling service](../../src/domain_kernel/sources/application/service.py),
[persistence design](../../docs/architecture/persistence-and-reliability.md#state-and-persistence)

| Method | Information a maintainer would otherwise have to find |
| --- | --- |
| `get` | SQLite raises `SourceNotFoundError` for an absent ID and `ScopeMismatchError` for an ID owned by another project. `Source` alone cannot express either outcome. |
| `find_by_name` | SQLite matches the exact lookup name within the project and returns `None` when it finds no match. The type shows that `None` is possible. The docstring can name the condition and distinguish the lookup name from a display label. |
| `save` | The service passes `None` to create a source and the previously read version to update it. SQLite rejects creation under an occupied project lookup name and raises `StaleStateError` when the guarded update matches no row. The service owns the transaction. |
| `list` | `None` starts pagination. SQLite requires a positive limit and a cursor from the same query. It orders by lookup name and provides a continuation when more results remain. Which parts of that paging behavior every adapter must preserve is a contract choice. [Page type](../../src/domain_kernel/shared/contracts.py) |

A short form could express the lookup rule in one sentence.

```python
"""Find a source by its exact project lookup name, or return None."""
```

A structured form gives the two meanings of `expected_version` and the
failure conditions separate places to read. This example describes the
checked SQLite behavior and transaction design. It illustrates a possible
port docstring if those behaviors are confirmed as shared promises.

```python
"""Create or update a project source in the caller's transaction.

Args:
    source: Source state to persist.
    expected_version: Pass None to create a source. To update a source, pass
        the version read before preparing the change.

Raises:
    SourceAlreadyExistsError: The project's lookup name is already taken.
    StaleStateError: The update finds no source at the expected version.
"""
```

## Decisions for the standards discussion

1. When should one informative sentence be sufficient, and which information
   should trigger named sections? Contrast the lookup with the versioned write
   before choosing where a short docstring stops serving the reader.
2. Which interfaces need their own caller and implementer documentation?
   Compare exported SDK calls, protocols implemented by a host, internal
   ports, and adapter overrides that add material behavior.
3. Which failures count as stable interface promises? Compare an expected
   write conflict with a documented precondition, such as using a continuation
   from the same query. Decide whether readers need both the restriction and
   the exception or only the restriction.
4. Which details belong next to the signature and which belong at the class or
   protocol level? Compare each method's absence or retry behavior with
   transaction ownership that applies to all repository writes.
5. When would a keyword-only usage example clarify a contract? Compare a
   subtle call sequence, such as reusing a returned cursor, with semantics
   that fit in an argument or result description. Consider where a reader
   would find the example in the current reference or a task guide.
