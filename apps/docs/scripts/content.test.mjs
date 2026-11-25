import assert from "node:assert/strict"
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { test } from "node:test"

import { validateContent } from "./content.mjs"

async function fixture(t, pages) {
  const root = await mkdtemp(path.join(tmpdir(), "inframeld-docs-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  for (const [route, content] of Object.entries(pages)) {
    const file = path.join(root, "src/app", route, "page.mdx")
    await mkdir(path.dirname(file), { recursive: true })
    await writeFile(file, content)
  }
  return root
}

test("reports a Markdown link to a route that does not exist", async (t) => {
  const root = await fixture(t, { "": "# Home\n\n[Missing](/missing)" })
  assert.match((await validateContent(root)).join("\n"), /\/missing.*route/)
})

test("reports broken section anchors in Markdown and MDX links", async (t) => {
  const root = await fixture(t, {
    "": '# Home\n\n[Missing](/guide#missing)\n\n<Button href="/guide#also-missing">Read</Button>',
    guide: "# Guide\n\n## Setup\n\nReady.",
  })
  const errors = await validateContent(root)
  assert.equal(errors.length, 2)
  assert.match(errors.join("\n"), /#missing.*anchor/)
  assert.match(errors.join("\n"), /#also-missing.*anchor/)
})

test("accepts real routes, duplicate heading slugs, reference links and assets", async (t) => {
  const root = await fixture(t, {
    "": '# Home\n\n[Guide][guide]\n\n[guide]: /guide#setup-2\n\n[Source](https://github.com/matejpalenik/domain-kernel)\n\n<Button href="/guide#setup">Read</Button>\n\n![Logo](/logo.svg)',
    guide: "# Guide\n\n## Setup\n\nFirst.\n\n## Setup\n\nSecond.\n\n[Home](/)",
  })
  await mkdir(path.join(root, "public"), { recursive: true })
  await writeFile(path.join(root, "public/logo.svg"), "<svg/>")
  assert.deepEqual(
    await validateContent(root, [{ links: [{ href: "/guide" }] }]),
    []
  )
})

test("checks navigation destinations even when no page links to them", async (t) => {
  const root = await fixture(t, { "": "# Home" })
  assert.match(
    (await validateContent(root, [{ links: [{ href: "/deleted" }] }])).join(
      "\n"
    ),
    /navigation.*\/deleted.*route/
  )
})

test("resolves relative links from trailing-slash page routes", async (t) => {
  const root = await fixture(t, {
    "": "# Home",
    guide: "# Guide\n\n[Child](child/#setup)\n\n[Home](../)",
    "guide/child": "# Child\n\n## Setup\n\n[Guide](../)",
  })
  assert.deepEqual(await validateContent(root), [])
})

test("checks child navigation destinations", async (t) => {
  const root = await fixture(t, { "": "# Home", cli: "# CLI" })
  const navigation = [
    { links: [{ href: "/cli", children: [{ href: "/missing" }] }] },
  ]
  assert.match(
    (await validateContent(root, navigation)).join("\n"),
    /navigation.*\/missing.*route/
  )
})

test("reports undocumented implemented symbols", async (t) => {
  const root = await fixture(t, {
    "": "# Reference",
  })
  const contract = {
    symbols: [{ name: "ProjectId" }],
  }
  const errors = (await validateContent(root, [], contract)).join("\n")
  assert.match(errors, /ProjectId.*not documented/)
})

test("generated reference makes public symbol anchors available", async (t) => {
  const root = await fixture(t, {
    "": "# Reference\n\n[Identifier](#ProjectId)\n\n<SdkReference />",
  })
  const contract = {
    symbols: [{ name: "ProjectId" }],
  }
  assert.deepEqual(await validateContent(root, [], contract), [])
})

test("validates fragments in public directory index assets", async (t) => {
  const root = await fixture(t, {
    "": "# Home\n\n[Chart](/resources/chart/#data)\n\n[Missing](/resources/chart/#missing)",
  })
  await mkdir(path.join(root, "public/resources/chart"), { recursive: true })
  await writeFile(
    path.join(root, "public/resources/chart/index.html"),
    '<h2 id="data">Data</h2>'
  )
  const errors = await validateContent(root)
  assert.equal(errors.length, 1)
  assert.match(errors[0], /missing.*anchor/)
})

test("reports invalid MDX rather than silently skipping its links", async (t) => {
  const root = await fixture(t, { "": "# Home\n\n<Note>Unclosed" })
  assert.match((await validateContent(root)).join("\n"), /MDX/)
})
