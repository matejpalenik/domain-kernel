import assert from "node:assert/strict"
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { test } from "node:test"
import { startPreview } from "./preview.mjs"

test("serves exported routes under the repository prefix and returns real 404s", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "domain-kernel-site-"))
  t.after(() => rm(directory, { recursive: true, force: true }))
  await mkdir(path.join(directory, "quickstart"))
  await writeFile(
    path.join(directory, "quickstart/index.html"),
    "<h1>Quickstart</h1>"
  )
  await writeFile(path.join(directory, "404.html"), "<h1>Page not found</h1>")
  const server = await startPreview({
    directory,
    port: 0,
    basePath: "/domain-kernel",
  })
  t.after(() => new Promise((resolve) => server.close(resolve)))
  const origin = `http://127.0.0.1:${server.address().port}`
  const route = await fetch(`${origin}/domain-kernel/quickstart/`)
  assert.equal(route.status, 200)
  assert.match(route.headers.get("content-type"), /text\/html/)
  assert.equal(await route.text(), "<h1>Quickstart</h1>")
  assert.equal((await fetch(`${origin}/quickstart/`)).status, 404)
  const missing = await fetch(`${origin}/domain-kernel/missing/`)
  assert.equal(missing.status, 404)
  assert.equal(await missing.text(), "<h1>Page not found</h1>")
  assert.equal(
    (await fetch(`${origin}/domain-kernel/%2e%2e%2fpackage.json`)).status,
    404
  )
})
