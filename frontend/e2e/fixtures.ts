/**
 * Stubbed API payloads for the browser suites. Nothing here calls a model or
 * touches the real database: the numbers are invented, but the *shape* is the
 * backend's, so a field rename in `openapi.json` shows up as a failing test
 * rather than as an empty card nobody notices.
 */
import type { Page } from "@playwright/test";

export const HEALTH = {
  status: "ok",
  database: "ok",
  gmail: "not_connected",
  llm: "ok",
  checked_at: "2026-11-13T07:00:00Z",
};

export const SETTINGS = {
  criteria: {
    include_keywords: ["backend", "platform"],
    exclude_keywords: ["unpaid"],
    locations: ["Remote"],
    seniority: ["senior"],
  },
  non_negotiables: {
    languages: ["Python"],
    locations: ["Indonesia"],
    work_modes: ["remote"],
    salary_floor: { amount: 20_000_000, currency: "IDR" },
    work_authorization: "Indonesian citizen",
  },
  llm: {
    base_url: "https://api.deepseek.com",
    model: "deepseek-v4-flash",
    runs: 3,
    temperature: 0.2,
    api_key_set: true,
  },
  budget: { monthly_tokens: 500_000 },
  redaction: { terms: ["Antonio"] },
};

export const SUMMARY = {
  counts: { cv: 2, job_posting: 3, app_setting: 1 },
  total_rows: 6,
  database: { path: "data\\cv-fit.db", files: 1, bytes: 233_472 },
  uploads: { path: "data\\uploads", files: 1, bytes: 2_048 },
  backups: { directory: "data\\backups", files: 0, latest: null },
};

/**
 * Anchored on the origin: a bare `**` glob also matches Vite's
 * `/src/api/*.ts` modules, which stops the app from booting at all.
 */
export function apiPattern(path: string): RegExp {
  return new RegExp(`^https?://[^/]+${path}$`);
}

export async function stubJson(
  page: Page,
  path: string,
  json: unknown,
  status = 200,
): Promise<void> {
  await page.route(apiPattern(path), (route) =>
    route.fulfill({ json, status }),
  );
}

/** Every read the settings screen makes. */
export async function stubSettings(page: Page): Promise<void> {
  await stubJson(page, "/api/settings", SETTINGS);
  await stubJson(page, "/api/data", SUMMARY);
  await stubJson(page, "/api/health", HEALTH);
}

/** The reads the shell and the two list screens make, with no rows stored. */
export async function stubEmptyApp(page: Page): Promise<void> {
  await stubJson(page, "/api/health", HEALTH);
  await stubJson(page, "/api/cvs", { items: [] });
  await stubJson(page, "/api/jobs", { items: [] });
  await stubJson(page, "/api/jobs/sync-status", { synced_at: null });
}
