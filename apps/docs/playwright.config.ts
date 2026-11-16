import { defineConfig } from "@playwright/test"

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/domain-kernel"

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:3094${basePath}/`,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "node scripts/preview.mjs",
    env: { PORT: "3094" },
    url: `http://127.0.0.1:3094${basePath}/`,
    reuseExistingServer: false,
  },
})
