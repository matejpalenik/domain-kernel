import { execFileSync, spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"

// Resolve the revision before Turbo hashes its environment, including local builds.
const root = fileURLToPath(new URL("../", import.meta.url))
const revision =
  process.env.DOCS_REVISION ??
  execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: root,
    encoding: "utf8",
  }).trim()
if (!/^[a-f0-9]{40}$/.test(revision))
  throw new Error("DOCS_REVISION must be a complete Git commit SHA")
const result = spawnSync("turbo", ["run", ...process.argv.slice(2)], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, DOCS_REVISION: revision },
})
if (result.error) throw result.error
process.exitCode = result.status ?? 1
