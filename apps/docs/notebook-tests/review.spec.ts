import { expect, test, type Locator, type Page } from "@playwright/test"

async function tableContrast(cell: Locator): Promise<number> {
  return cell.evaluate((element) => {
    const channels = (color: string) =>
      (color.match(/\d+(?:\.\d+)?/g) ?? []).map(Number)
    const luminance = (color: number[]) => {
      const [red = 0, green = 0, blue = 0] = color.slice(0, 3).map((value) => {
        const normalized = value / 255
        return normalized <= 0.04045
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * red + 0.7152 * green + 0.0722 * blue
    }
    const foreground = luminance(channels(getComputedStyle(element).color))
    let background = 1
    for (let node: Element | null = element; node; node = node.parentElement) {
      const values = channels(getComputedStyle(node).backgroundColor)
      if (values.length === 3 || (values[3] ?? 0) === 1) {
        background = luminance(values)
        break
      }
    }
    return (
      (Math.max(foreground, background) + 0.05) /
      (Math.min(foreground, background) + 0.05)
    )
  })
}

async function setTheme(page: Page, theme: "Light" | "Dark") {
  await page.getByText("Settings", { exact: true }).click()
  await page.getByText("Theme", { exact: true }).hover()
  await page.getByText("JupyterLab " + theme, { exact: true }).click()
  await expect(page.locator("body")).toHaveAttribute(
    "data-jp-theme-light",
    theme === "Light" ? "true" : "false"
  )
}

async function waitForKernel(page: Page) {
  const lab = page.url().includes("/lab/")
  if (!lab) {
    const picker = page.getByRole("dialog").getByRole("button", {
      name: "Select Kernel",
    })
    const selected = page.getByRole("button", { name: "Python 3 (ipykernel)" })
    await expect(picker.or(selected).first()).toBeVisible({ timeout: 20_000 })
    if (await picker.isVisible()) await picker.click()
    await expect(selected).toBeVisible({ timeout: 20_000 })
  }
  const idle = lab
    ? page.getByRole("button", { name: /\| Idle$/ })
    : page.locator('.jp-Notebook-ExecutionIndicator[data-status="idle"]')
  await expect(idle).toBeAttached({ timeout: 20_000 })
}

test("open and run the evidence-first tour", async ({
  page,
  baseURL,
}, testInfo) => {
  test.setTimeout(120_000)
  if (!baseURL) throw new Error("Select a configured notebook frontend")
  await page.setViewportSize({ width: 760, height: 950 })
  await page.goto(
    baseURL.replace("acceptance.ipynb", "domain-kernel-tour.ipynb")
  )
  await expect(
    page.getByRole("heading", { name: "Read the evidence" })
  ).toBeVisible()
  await waitForKernel(page)
  await page.getByText("Run", { exact: true }).click()
  await page.getByText("Run All Cells", { exact: true }).click()
  await expect(
    page.getByText(/Complete published model · 1\.0\.0 · 5 definitions/)
  ).toBeVisible({
    timeout: 90_000,
  })

  await setTheme(page, "Dark")
  await page
    .getByRole("heading", { name: "Read the evidence" })
    .scrollIntoViewIfNeeded()
  await expect(
    page
      .locator(".jp-OutputArea-output")
      .filter({ hasText: "full text read back from SQLite" })
  ).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("walkthrough-dark.png") })
})

test("inspect the release and submit an explicitly previewed review", async ({
  page,
  baseURL,
}) => {
  if (!baseURL) throw new Error("Select a configured notebook frontend")
  await page.goto(baseURL.replace("/lab/tree/", "/lab/workspaces/review/tree/"))
  await waitForKernel(page)
  await page
    .getByRole("button", { name: "Restart the kernel and run all cells" })
    .click()
  await page.getByRole("button", { name: "Confirm Kernel Restart" }).click()

  const table = page.getByRole("table", { name: "DomainModelBundle" })
  await expect(table.getByText("1.1.0", { exact: true })).toBeVisible({
    timeout: 30_000,
  })
  const search = page.getByRole("textbox", { name: "Search definitions" })
  await search.fill("recruitment-ai-system")
  await expect(
    page
      .getByRole("table", { name: "Definition" })
      .getByRole("row", { name: "Definition recruitment-ai-system" })
  ).toBeVisible()

  const reason = page.getByRole("textbox", { name: "Review reason" })
  const preview = page.getByRole("button", { name: "Preview review" })
  const submit = page.getByRole("button", { name: "Submit review" })
  await expect(
    page.getByText("Reviewer browser-reviewer", { exact: true })
  ).toBeVisible()
  await expect(submit).toBeDisabled()
  await reason.fill("Verify the receiving application.")
  await expect(preview).toBeEnabled()
  await page.keyboard.press("Tab")
  await expect(preview).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(
    page.getByText("Preview ready for explicit submission.")
  ).toBeVisible()
  await reason.fill("Verify the exact publication handoff.")
  await expect(submit).toBeDisabled()
  await preview.focus()
  await page.keyboard.press("Enter")
  await expect(submit).toBeEnabled()
  await submit.focus()
  await page.keyboard.press("Enter")
  await expect(
    page.getByText(/Decision recorded by browser-reviewer/)
  ).toBeVisible()
  await expect(submit).toBeDisabled()
  await expect(page.getByText("Code fallback · Release 1.1.0")).toBeVisible()

  await setTheme(page, "Light")
  const releaseCell = table.getByRole("cell", { name: "1.1.0" })
  expect(await tableContrast(releaseCell)).toBeGreaterThanOrEqual(4.5)
  const light = await table.evaluate(
    (element) => getComputedStyle(element).color
  )
  await setTheme(page, "Dark")
  await expect
    .poll(() => table.evaluate((element) => getComputedStyle(element).color))
    .not.toBe(light)
  await expect(table.getByText("Release", { exact: true })).toBeVisible()
  expect(await tableContrast(releaseCell)).toBeGreaterThanOrEqual(4.5)
})
