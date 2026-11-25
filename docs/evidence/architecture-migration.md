# Architecture documentation migration

## What moved

The [root overview](../../ARCHITECTURE.md) now describes the SDK's boundaries,
design decisions, and cross-cutting guarantees. The
[contract index](../architecture/README.md) routes maintainers to twelve
chapters. The previous monolith supplied their detailed requirements.

| Contract                                                 | Owner                                                                                           |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Product boundary and operational data                    | [Scope](../architecture/scope.md)                                                               |
| Lifecycle slices, dependencies, and application boundary | [Components and ownership](../architecture/components-and-ownership.md)                         |
| Public handles, configuration, identity, and names       | [Workspace and configuration](../architecture/workspace-and-configuration.md)                   |
| Source capture and evidence provenance                   | [Sources and evidence](../architecture/sources-and-evidence.md)                                 |
| Drafting, reconciliation, and recovery inputs            | [Discovery and reconciliation](../architecture/discovery-and-reconciliation.md)                 |
| Reference packs, typed definitions, and authoring        | [Reference knowledge and domain types](../architecture/reference-knowledge-and-domain-types.md) |
| Review, readiness, and release                           | [Review and publication](../architecture/review-and-publication.md)                             |
| Wire contract, consumption, and projections              | [Bundles and interoperability](../architecture/bundles-and-interoperability.md)                 |
| Corrections, coordinated changes, and dependencies       | [Model evolution](../architecture/model-evolution.md)                                           |
| Notebook and backend use of persisted workflows          | [Host integration](../architecture/host-integration.md)                                         |
| Transactions, retention, limits, and replay              | [Persistence and reliability](../architecture/persistence-and-reliability.md)                   |
| Failure contracts, verification, and future extensions   | [Guarantees and verification](../architecture/guarantees-and-verification.md)                   |

Updated the root README, contribution and security guides, `AGENTS.md`,
Domain Kernel skills and their references, documentation and discovery
guides, configuration recipes, notebook guide, and conformance and
release-acceptance references. The website's
[Concepts and design page](../../apps/docs/src/app/concepts/page.mdx) links to
the contract index at the site's source revision. The portable tour archive
ships the new Markdown chapters. Site navigation and archive tests cover those
changes. No SDK implementation, dependency configuration, public exports, or
notebook bytes changed in this migration.

The old fragments still land on the root page with links to the chapter that
now owns the section. Inbound links in maintained docs point directly to the
new location. The two identically titled reference-pack sections had separate
legacy fragments, which now route to the two corresponding chapters. The
temporary `architecture-migration/` proposal was removed after integration.

## Discrepancies resolved

- **PostgreSQL:** The proposal left availability unverified. The checkout
  provides the `postgres` extra and asynchronous Psycopg adapter. Its contract
  still requires explicit provisioning and forbids fallback to SQLite.
- **LinkML:** The bounded `dk-linkml/1.0` import and projection are implemented
  behind the `linkml` extra. The documentation distinguishes them from
  broader prospective mappings and from generic schema or data round trips.
- **Discovery and evidence:** The current whole-question path proposes
  concepts, relationships, and clarification questions. Typed constraints can
  be authored and reviewed, but this path does not materialize them. Bundles
  retain citations and review records, not a guarantee that originals have
  been retained or will stay available.
- **Ownership and examples:** The five lifecycle slices do not imply five
  services or identical package layouts. The supporting `reference_packs`
  package owns pack content and catalogs. The moved examples now use the
  implemented ontology syntax selector and pattern review preview.
- **Design versus evidence:** The root's rationale explains the documented
  design and its trade-offs; it is not a record of historical decisions or
  measured capacity. A reviewer, not a semantic equivalence check, decides
  whether a clarification should preserve a definition's identity. Future
  interoperability work remains labelled as such.

No architectural decision needed maintainer approval for this migration.
Broadening discovery output, adopting new formal semantics, or relaxing
consistency or readiness rules would require separate decisions and evidence.

## Verification and limits

- `UV_OFFLINE=true pnpm check` passed all 12 tasks: 795 SDK tests passed,
  31 skipped, and 7 deselected; 7 notebook tests, 13 website unit tests, and
  5 Chromium tests passed. The website built and its routes and navigation
  passed the content gate. The first run stopped on two README code-formatting
  differences, now fixed.
- `pnpm exec prettier --check ARCHITECTURE.md 'docs/architecture/*.md'` and
  `git diff --check` passed.
- A CommonMark-based audit checked 390 relative Markdown, notebook, and
  website repository links; 263 mapped destinations and 263 rendered legacy
  anchors resolved. The audit cross-checked moved text against the baseline
  and reviewed differences for changed status, examples, or navigation.
- Static review parsed 54 Python excerpts and checked 45 public imports and
  157 call signatures. The generated reference contains 465 source-backed
  entries; all example imports resolve and 41 distinct handle methods were
  found in their linked source. The excerpts were not executed.
- The archive built twice with identical bytes. It contained 105 entries
  including all 13 architecture files with exact bytes and no proposal files.
  The archive tests also reject unrelated files.
- All 17 Mermaid fences and diagram headers were checked. The repository
  has no Mermaid renderer in its check pipeline; rendering on GitHub was not
  verified. Revision-pinned site links were checked in Chromium and their
  targets locally. No site was published.

Live PostgreSQL cases needed a disposable DSN and were skipped in this run.
Pinned OCR, manufacturing, and ROBOT cases also require separate provisioned
inputs. Replayed inference and notebook fixtures do not establish live
discovery quality or release acceptance.
