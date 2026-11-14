import { expect, test, type Page } from "@playwright/test";

import { stubJson, stubSettings } from "./fixtures";

/**
 * Settings against a stubbed API. The purge is never sent: this suite must not
 * depend on, and must never destroy, a real database. What it does assert is
 * that the gate in front of the purge cannot be walked around, and that the
 * figures shown are the server's rather than a guess.
 */

async function openPrivacy(page: Page): Promise<void> {
  await page.goto("/settings");
  await page.getByRole("tab", { name: "Privacy and data" }).click();
}

test("settings: four tabs, and the stored document is the one shown", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await stubSettings(page);

  await page.goto("/settings");

  await expect(
    page.getByRole("heading", { level: 1, name: "Settings" }),
  ).toBeVisible();
  for (const name of ["Criteria", "Model", "Privacy and data", "Gmail"]) {
    await expect(page.getByRole("tab", { name })).toBeVisible();
  }

  // An untouched form is not dirty, so Save must refuse to pretend otherwise.
  await expect(page.getByLabel("Include keywords")).toHaveValue(
    "backend, platform",
  );
  await expect(page.getByLabel("Exclude keywords")).toHaveValue("unpaid");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await expect(page.getByText("Unsaved changes")).toHaveCount(0);

  await page.getByRole("tab", { name: "Model" }).click();
  await expect(page.getByLabel("Base URL")).toHaveValue(
    "https://api.deepseek.com",
  );
  await expect(
    page.getByRole("textbox", { name: "Model", exact: true }),
  ).toHaveValue("deepseek-v4-flash");
  // The key itself is never sent back, so the field is empty and says why.
  await expect(page.getByLabel("API key")).toHaveValue("");
  await expect(page.getByLabel("API key")).toHaveAttribute(
    "placeholder",
    /A key is stored/,
  );
  await expect(page.getByText("0.20")).toBeVisible();

  await page.getByRole("tab", { name: "Criteria" }).click();
  await expect(page.getByLabel("Include keywords")).toHaveValue(
    "backend, platform",
  );

  expect(pageErrors).toEqual([]);
});

test("settings: the purge cannot be reached without typing the word", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const purges: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/data/purge")) {
      purges.push(request.method());
    }
  });
  await stubSettings(page);

  await openPrivacy(page);

  // The honest data figures, straight from `GET /api/data`.
  await expect(page.getByText("6 rows, 228.0 kB")).toBeVisible();
  await expect(page.getByText("1 file, 2.0 kB")).toBeVisible();
  await expect(page.getByText(/data\\backups/)).toBeVisible();
  await expect(page.getByText("api.deepseek.com")).toBeVisible();

  await page.getByRole("button", { name: "Delete all data" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete everything" });
  await expect(dialog).toBeVisible();

  // Exact counts, and settings deliberately absent: they survive a purge.
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  await expect(dialog.getByText("CVs")).toBeVisible();
  await expect(dialog.getByText("Job posts")).toBeVisible();
  await expect(
    dialog.getByText(/Settings and non-negotiables are kept/),
  ).toBeVisible();

  const confirm = dialog.getByRole("button", { name: "Delete everything" });
  await expect(confirm).toBeDisabled();

  const word = dialog.getByRole("textbox", { name: "Type DELETE to confirm" });
  await word.fill("delete");
  await expect(confirm).toBeDisabled();
  await word.fill("DELETE");
  await expect(confirm).toBeEnabled();

  // Closing must clear the word, or reopening would land on an armed button.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Delete all data" }).click();
  await expect(
    page.getByRole("textbox", { name: "Type DELETE to confirm" }),
  ).toHaveValue("");

  expect(purges).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("settings: the Gmail tab reports state and hands over the command", async ({
  page,
}) => {
  await stubSettings(page);
  await stubJson(
    page,
    "/api/gmail/connect",
    {
      code: "GMAIL_NOT_CONNECTED",
      message: "No Google account is connected yet.",
      details: { command: "uv run mcp-gmail auth" },
      request_id: "req-1",
    },
    400,
  );

  await page.goto("/settings");
  await page.getByRole("tab", { name: "Gmail" }).click();

  await expect(page.getByText("Not connected")).toBeVisible();
  await expect(page.getByText("gmail.readonly")).toBeVisible();
  await expect(page.getByRole("button", { name: "Disconnect" })).toBeDisabled();

  await page.getByRole("button", { name: "Check connection" }).click();

  // The advice is a command to run, not a button that can never work.
  await expect(
    page.getByText("Run this in a terminal, then check again:"),
  ).toBeVisible();
  await expect(page.getByText("uv run mcp-gmail auth")).toBeVisible();
});
