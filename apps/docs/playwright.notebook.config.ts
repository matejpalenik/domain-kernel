import { defineConfig } from "@playwright/test"
import { fileURLToPath } from "node:url"

const root = fileURLToPath(new URL("../..", import.meta.url))
const token = "domain-kernel-browser-fixture"

const frontends = [
  { name: "jupyterlab", port: 8793, path: "/lab/tree/acceptance.ipynb" },
  { name: "notebook", port: 8794, path: "/notebooks/acceptance.ipynb" },
]

export default defineConfig({
  testDir: "./notebook-tests",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 60_000,
  projects: frontends.map(({ name, port, path }) => ({
    name,
    use: { baseURL: `http://127.0.0.1:${port}${path}?token=${token}` },
  })),
  webServer: frontends.map(({ name, port }) => ({
    command: `.venv/bin/python -m development.notebook_frontends ${name} --port ${port}`,
    cwd: root,
    env: { DK_TEST_JUPYTER_TOKEN: token },
    url: `http://127.0.0.1:${port}/api/status?token=${token}`,
    reuseExistingServer: false,
    timeout: 45_000,
  })),
  use: { trace: "retain-on-failure" },
})
