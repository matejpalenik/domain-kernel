import { expect, test, type Locator } from "@playwright/test"

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

test("inspect the release and submit an explicitly previewed review", async ({
  page,
  baseURL,
}) => {
  if (!baseURL) throw new Error("Select a configured notebook frontend")
  await page.goto(baseURL)
  const editor = page.locator(".jp-CodeCell .cm-content").first()
  await editor.click()
  await page.keyboard.press("Shift+Enter")

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

  const releaseCell = table.getByRole("cell", { name: "1.1.0" })
  expect(await tableContrast(releaseCell)).toBeGreaterThanOrEqual(4.5)
  const light = await table.evaluate(
    (element) => getComputedStyle(element).color
  )
  await page.getByText("Settings", { exact: true }).click()
  await page.getByText("Theme", { exact: true }).hover()
  await page.getByText("JupyterLab Dark", { exact: true }).click()
  await expect(page.locator("body")).toHaveAttribute(
    "data-jp-theme-light",
    "false"
  )
  await expect
    .poll(() => table.evaluate((element) => getComputedStyle(element).color))
    .not.toBe(light)
  await expect(table.getByText("Release", { exact: true })).toBeVisible()
  expect(await tableContrast(releaseCell)).toBeGreaterThanOrEqual(4.5)
})
