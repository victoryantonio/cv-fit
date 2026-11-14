import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { stubEmptyApp, stubSettings } from "./fixtures";

/**
 * WCAG 2.2 AA on every screen that exists, in both palettes.
 *
 * `color-contrast` is included on purpose. `src/styles/tokens.test.ts` proves
 * the token pairs are legible in the abstract; only a browser knows which pair
 * a component actually rendered. The tags are WCAG levels only: best-practice
 * rules are opinions, and a suite that fails on opinions gets muted.
 */
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const SCREENS = [
  { path: "/", name: "Home" },
  { path: "/jobs", name: "Jobs" },
  { path: "/cvs", name: "CVs" },
  { path: "/settings", name: "Settings" },
] as const;

const THEMES = ["light", "dark"] as const;

async function setTheme(page: Page, theme: string): Promise<void> {
  // Before any app script runs, so the first paint is already correct.
  await page.addInitScript((value) => {
    window.localStorage.setItem("cv-fit.theme", value);
  }, theme);
}

for (const theme of THEMES) {
  for (const screen of SCREENS) {
    test(`a11y: ${screen.name} meets WCAG 2.2 AA (${theme})`, async ({
      page,
    }) => {
      await stubEmptyApp(page);
      await stubSettings(page);
      await setTheme(page, theme);

      await page.goto(screen.path);

      // Scan the loaded screen, never a skeleton: a spinner has no contrast.
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

      const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();

      // A rule that never runs cannot fail. Contrast is the one rule axe skips
      // when it cannot resolve a background, so require a verdict, not a pass.
      expect(
        results.incomplete.filter((rule) => rule.id === "color-contrast"),
      ).toEqual([]);

      // Rule ids and node counts, not axe's whole JSON: a failure should say
      // what broke without burying the test report.
      const violations = results.violations.map(
        (violation) => `${violation.id} (${violation.nodes.length} nodes)`,
      );
      expect(violations).toEqual([]);
    });
  }
}
