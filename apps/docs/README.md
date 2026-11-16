# Domain Kernel documentation

Next.js App Router and MDX documentation, adapted from Inframeld's Tailwind Plus
Protocol implementation. The template license is preserved in [LICENSE.md](LICENSE.md).
The website is an end product, not a template library.

Run from the repository root:

```sh
pnpm dev:docs
pnpm check:docs
pnpm build:docs
pnpm preview:docs
```

Development and exported previews use `http://localhost:3001/domain-kernel/`.
Root commands prepare Python reference data and notebook assets before Next.js
starts. Webpack is intentional: the Protocol search index uses its custom loader.

See [documentation maintenance](../../docs/documentation.md) for setup, content
ownership, checks, caching, manual GitHub Pages publication and recovery.
