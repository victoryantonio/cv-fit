import { expect, test, type Page } from "@playwright/test";

/**
 * B0 smoke test. The API is blocked inside the browser rather than assumed
 * absent: the shell must degrade honestly whenever the API cannot be reached,
 * and the suite has to give the same answer whether or not a server happens to
 * be running on the developer's machine.
 */
function blockApi(page: Page) {
  // Anchored on the origin: a bare `**/api/**` also matches Vite's own
  // `/src/api/client.ts` module, which stops the app from booting at all.
  return page.route(/^https?:\/\/[^/]+\/api\//, (route) => route.abort());
}

test("smoke: the shell renders without a backend", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await blockApi(page);

  await page.goto("/");

  await expect(
    page.getByRole("heading", { level: 1, name: "Home" }),
  ).toBeVisible();
  await expect(page.getByText("CV to job fit")).toBeVisible();
  await expect(page.getByText("Cannot reach the local server.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test("smoke: the theme toggle switches the palette attribute", async ({
  page,
}) => {
  await page.goto("/");

  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await page.getByRole("button", { name: /Switch to .* theme/ }).click();
  await expect(html).not.toHaveAttribute("data-theme", before ?? "");
});

test("smoke: the rail reaches the CV screen and the screen degrades", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await blockApi(page);

  await page.goto("/");

  await page.getByRole("link", { name: "CVs" }).click();

  await expect(page).toHaveURL(/\/cvs$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "CVs" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add a CV" })).toBeVisible();
  await expect(page.getByLabel("Label")).toBeVisible();
  await expect(page.getByText("Cannot reach the local server.")).toBeVisible();
  await expect(page.getByRole("link", { name: "CVs" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  expect(pageErrors).toEqual([]);
});

test("smoke: the rail reaches the jobs screen and it says how text gets in", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await blockApi(page);

  await page.goto("/");

  await page.getByRole("link", { name: "Jobs" }).click();

  await expect(page).toHaveURL(/\/jobs$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Jobs" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Nothing is fetched from the site for you/),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Add a job" })).toBeVisible();
  await expect(page.getByText("Cannot reach the local server.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Jobs" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  expect(pageErrors).toEqual([]);
});
