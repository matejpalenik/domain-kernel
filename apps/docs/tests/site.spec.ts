import { expect, test, type Page } from "@playwright/test"

async function openSearch(page: Page) {
  const input = page.getByPlaceholder("Find something...")
  // The navigation is visible before the suspended dialog registers its shortcut.
  await expect(async () => {
    if (!(await input.isVisible())) {
      await page.keyboard.press("ControlOrMeta+k")
    }
    await expect(input).toBeVisible({ timeout: 250 })
  }).toPass({ timeout: 5_000 })
  return input
}

test("direct routes, reloads, assets and missing pages work on the project URL", async ({
  page,
}) => {
  const failures: string[] = []
  page.on("pageerror", (error) => failures.push(error.message))
  page.on("response", (response) => {
    if (response.status() >= 400 && response.url().includes("/_next/"))
      failures.push(response.url())
  })
  for (const route of [
    "",
    "quickstart/",
    "tour/",
    "reference/",
    "concepts/",
    "contributing/",
  ]) {
    const response = await page.goto(route)
    expect(response?.status()).toBe(200)
    await expect(page.locator("h1")).toBeVisible()
    await page.reload()
    await expect(page.locator("h1")).toBeVisible()
  }
  expect(failures).toEqual([])
  const missing = await page.goto("not-a-page/")
  expect(missing?.status()).toBe(404)
  await expect(
    page.getByRole("heading", { name: "Page not found" })
  ).toBeVisible()
})

test("search finds implemented symbols and notebook chapters with working destinations", async ({
  page,
}) => {
  await page.goto("")
  await expect(
    page.getByRole("button", { name: /Find something.*K/ })
  ).toBeVisible()
  await (await openSearch(page)).fill("ProjectId")
  await expect(page.getByRole("option").first()).toContainText("ProjectId")
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/reference\/#ProjectId$/)
  await expect(page.locator("#ProjectId")).toBeInViewport()
  await (await openSearch(page)).fill("Parse the evidence")
  await expect(page.getByRole("option").first()).toContainText(
    "Parse the evidence"
  )
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/tour\/reading\/#c3$/)
  await expect(
    page.getByRole("heading", { name: /C3 · Parse the evidence/ })
  ).toBeInViewport()
  await expect(page.locator("body")).toContainText("simulated")
})

test("theme controls, keyboard skip link and copy buttons are usable", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await page.goto("quickstart/")
  await page.keyboard.press("Tab")
  await expect(
    page.getByRole("link", { name: "Skip to content" })
  ).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(page.locator("#main-content")).toBeFocused()
  const toggle = page.getByRole("button", { name: /Switch to .* theme/ })
  await toggle.click()
  const dark = await page
    .locator("html")
    .evaluate((element) => element.classList.contains("dark"))
  await toggle.click()
  expect(
    await page
      .locator("html")
      .evaluate((element) => element.classList.contains("dark"))
  ).toBe(!dark)
  await page.getByRole("button", { name: /Copy/i }).first().click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "git clone"
  )
})

test("mobile navigation and the static tour remain readable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("")
  await page.getByRole("button", { name: "Toggle navigation" }).click()
  await page
    .getByRole("dialog")
    .getByRole("link", { name: "Developer tour", exact: true })
    .click()
  await expect(page).toHaveURL(/\/tour\/$/)
  await expect(
    page.getByRole("heading", { name: "From legislation to a reusable model" })
  ).toBeVisible()
  const archive = page.getByRole("link", {
    name: /Download the matching source/,
  })
  await expect(archive).toHaveAttribute("href", /\/archive\/[a-f0-9]{40}\.zip$/)
  await page.getByRole("link", { name: /Read the complete tour/ }).click()
  await expect(page.locator("body")).toContainText("Interactive preview")
  await expect(page.locator("#c1")).toBeAttached()
  await expect(page.locator("#r1")).toBeAttached()
  const inspection = page.locator('[id="cell-id=e10-preview"]')
  await expect(
    inspection.getByRole("table", { name: "Publication" })
  ).toBeVisible()
  await expect(inspection).toContainText("Code fallback: recruitment-ai-system")
  await page.goto("reference/")
  expect(
    await page.evaluate(() => document.body.scrollWidth)
  ).toBeLessThanOrEqual(390)
})
