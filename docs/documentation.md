# Documentation development and publication

The documentation website lives beside the Python SDK. uv owns Python dependencies;
pnpm owns website dependencies. Turbo coordinates tasks without moving the SDK or
adding Node to its runtime requirements.

The Next.js and MDX site is adapted from Inframeld's Tailwind Plus Protocol
implementation and is an end product, not a template library. See the
[template license](https://github.com/matejpalenik/domain-kernel/blob/main/apps/docs/LICENSE.md).
Webpack is required by the Protocol search index's custom loader.

## Set up and run

Use the versions in `mise.toml`. From the repository root:

```sh
mise install
pnpm install --frozen-lockfile
pnpm --filter @domain-kernel/docs exec playwright install chromium
pnpm dev:docs
```

Open `http://localhost:3001/domain-kernel/`. The default base path matches GitHub
Pages, so development exposes incorrect root-relative links early.

```sh
pnpm check:docs
pnpm build:docs
pnpm preview:docs
```

The preview serves exported files, including genuine 404 responses. It does not
start a Next.js application server. Chromium is needed for browser acceptance;
Linux CI provisions its system dependencies with Playwright's `--with-deps` option.

## Content ownership

- MDX pages own the website's introductions, tasks and explanations.
- Implemented Python exports own the generated SDK reference. The source reader
  follows local inheritance, explicit initializers, annotations, enum values and
  type aliases. Class declarations are displayed when Python generates the initializer.
- The [interactive notebook](../examples/notebooks/README.md) owns the end-to-end
  walkthrough and its setup. The website links to the run guide at its build
  revision. It neither executes nor exports the notebook.
- [Architecture](../ARCHITECTURE.md) owns the system overview and cross-cutting decisions.
  The [architecture chapters](architecture/README.md) own detailed contracts. The
  [configuration recipes](../examples/config/README.md) provide runnable setup examples.

The website's generated data is ignored by Git and excluded from Python
distributions. For an older checkout that built the retired tour, remove the
generated `apps/docs/public/tour/reading/index.html` before rebuilding; Next.js
copies any files that remain under `public/`. If Next.js type checking still
mentions the retired layout, discard the generated `apps/docs/.next/` cache.

## Tasks and caching

Root commands resolve the Git revision before invoking Turbo, so source links
participate in the cache identity. CI passes its checked-out
revision explicitly. `NEXT_PUBLIC_BASE_PATH` and `DOCS_SITE_URL` are also cache
inputs; their defaults target the initial project URL.

Turbo provisions the locked Python environment once per invocation. Subsequent
Python tasks use `uv run --locked --no-sync`, preventing parallel reconciliation.
Existing direct uv commands remain supported.

Only deterministic website tasks use the local Turbo cache. Python verification,
notebook execution, browser tests, audits and deployment remain uncached. Remote
caching is disabled. No virtual environments are cached by Turbo.

## Author and verify

Add a `page.mdx` and matching server metadata layout, then add its route to the
navigation JSON. Use existing callouts, code groups and typography. Explain the
reader's goal, show a supported action and interpret its result.

The content gate compiles MDX and checks routes, anchors, assets and reference
coverage. Python example tests execute complete Python
blocks in the quickstart and reference pages. Browser tests cover deep links,
search, copying, keyboard use, themes and mobile navigation.

Formatting is scoped to the website and explicit tooling files. Protocol-derived
code retains `apps/docs/LICENSE.md`; it is not relicensed as the Apache-2.0 SDK or
distributed as a reusable template package.

## Publish manually

Merging does not publish documentation. Once changes are on `main`, select
**Actions → CI → Run workflow**, select `main`, and enable **Publish validated
documentation from main to GitHub Pages**. The CLI equivalent is:

```sh
gh workflow run ci.yml --ref main -f publish_docs=true
```

The run repeats required validation and uploads its exact static artifact.
Deployment runs only after those jobs succeed. Pages and OIDC permissions are
confined to deployment, and the `github-pages` environment accepts only `main`.
A publication request from another branch fails validation.

Check the deployment result and open `https://matejpalenik.github.io/domain-kernel/`.
Verify the quickstart, a nested reference anchor, search and source links. The
site is not considered published until that manual run succeeds.

Repository settings must be applied and read back as described in
[Repository security settings](../.github/security-settings.md). Workflow files
alone cannot activate Pages or protections. Branch and release-tag rules remain.

## Recover a publication

Revert the faulty source change through a normal pull request, pass required
checks, then manually publish the corrected `main`. Python releases are independent.
