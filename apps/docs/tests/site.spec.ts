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
  await page.goto("concepts/")
  const architecture = page.getByRole("link", {
    name: "Architecture",
    exact: true,
  })
  await expect(architecture).toHaveAttribute(
    "href",
    /\/blob\/[a-f0-9]{40}\/ARCHITECTURE\.md$/
  )
  await expect(
    page.getByRole("link", { name: "document discovery guide", exact: true })
  ).toHaveAttribute(
    "href",
    /\/blob\/[a-f0-9]{40}\/docs\/architecture\/discovery-and-reconciliation\.md$/
  )
  await expect(
    page.getByRole("link", { name: "architecture contract index", exact: true })
  ).toHaveAttribute(
    "href",
    /\/blob\/[a-f0-9]{40}\/docs\/architecture\/README\.md$/
  )
  await page.getByRole("link", { name: "implemented reference" }).click()
  await expect(page).toHaveURL(/\/reference\/$/)
  expect(failures).toEqual([])
  const missing = await page.goto("not-a-page/")
  expect(missing?.status()).toBe(404)
  await expect(
    page.getByRole("heading", { name: "Page not found" })
  ).toBeVisible()
})

test("the retired tour routes are not exported or linked", async ({ page }) => {
  for (const route of ["tour/", "tour/reading/"]) {
    const response = await page.goto(route)
    expect(response?.status()).toBe(404)
  }
  await page.goto("")
  await expect(page.locator('a[href*="/tour"]')).toHaveCount(0)
  await (await openSearch(page)).fill("Notebook reading version")
  await expect(page.getByText("Nothing found for")).toBeVisible()
})

test("search finds implemented symbols and guide sections with working destinations", async ({
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
  await (await openSearch(page)).fill("Install from source")
  await expect(page.getByRole("option").first()).toContainText(
    "Install from source"
  )
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/quickstart\/#install-from-source$/)
  await expect(
    page.getByRole("heading", { name: "Install from source" })
  ).toBeInViewport()
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

test("mobile navigation and guide pages remain readable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("")
  await page.getByRole("button", { name: "Toggle navigation" }).click()
  await page
    .getByRole("dialog")
    .getByRole("link", { name: "Quickstart", exact: true })
    .click()
  await expect(page).toHaveURL(/\/quickstart\/$/)
  await expect(
    page.getByRole("heading", {
      name: "Publish a reviewed recruitment model",
    })
  ).toBeVisible()
  await expect(
    page.getByRole("link", { name: "document discovery guide" })
  ).toHaveAttribute(
    "href",
    /\/blob\/[a-f0-9]{40}\/docs\/architecture\/discovery-and-reconciliation\.md$/
  )
  await page.emulateMedia({ colorScheme: "dark" })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth)
  ).toBeLessThanOrEqual(390)
  await page.goto("reference/")
  expect(
    await page.evaluate(() => document.body.scrollWidth)
  ).toBeLessThanOrEqual(390)
})
