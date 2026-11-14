import { expect, test, type Page } from "@playwright/test";

/**
 * The packet screen against a stored payload, not a model call. The API is
 * stubbed so the assertions are about rendering: section order, the sticky
 * nav's scroll-spy, and the fact that the guard's rejections are one click
 * away rather than gone. Numbers are the server's; nothing is recomputed here.
 */
const PACKET = {
  id: "a1",
  status: "ok",
  model: "deepseek-v4-flash",
  prompt_bundle: "match.v3-and-more-hash-text-here",
  match_runs: 3,
  cache_key: "abc",
  created_at: "2026-11-07T10:00:00Z",
  cv_version_id: "v1",
  extraction_id: "x1",
  snapshot_id: "s1",
  job_id: "j1",
  job: { title: "Backend Engineer", company: "Northwind" },
  requirements: [
    {
      id: "r1",
      position: 1,
      text: "Python services",
      importance: "weight",
      active: true,
    },
    {
      id: "r2",
      position: 2,
      text: "Kubernetes operations",
      importance: "knockout",
      active: true,
    },
  ],
  matches: [
    {
      requirement_id: "r1",
      verdict: "strong",
      evidence_quote: "Built Python services",
      rationale: null,
      votes: { strong: 3 },
      agreement: 1,
      flags: [],
    },
    {
      requirement_id: "r2",
      verdict: "gap",
      evidence_quote: null,
      rationale: null,
      votes: { gap: 3 },
      agreement: 1,
      flags: [],
    },
  ],
  summary: {
    label: "stretch",
    coverage: 50,
    counts: { strong: 1, partial: 0, gap: 1 },
    must_have: { met: 0, total: 1, coverage: 0 },
    knockout_gaps: [{ requirement_id: "r2", text: "Kubernetes operations" }],
    strongest: [
      {
        requirement_id: "r1",
        text: "Python services",
        evidence_quote: "Built Python services",
      },
    ],
    biggest_gaps: [
      { requirement_id: "r2", text: "Kubernetes operations", verdict: "gap" },
    ],
    unstable_count: 0,
    constraint_flags: [
      {
        kind: "work_mode",
        status: "conflict",
        note: "Post is onsite",
        jd_value: "onsite",
        user_value: "remote",
      },
      {
        kind: "salary",
        status: "not_stated",
        note: "You have not set a salary floor.",
        jd_value: null,
        user_value: null,
      },
    ],
  },
  suggestions: [
    {
      id: "s1",
      requirement_id: "r1",
      type: "reword",
      scope: "job_specific",
      target_section: "experience",
      original_text: "Built Python services",
      proposed_text: "Built Python services for two teams",
      rationale: "Names the team scope the post asks about",
      guard_status: "pass",
      guard_reason: null,
      decision: "pending",
      decision_reason: null,
    },
  ],
  suggestion_provenance: {
    total: 2,
    visible: 1,
    hidden: 1,
    rejected_by_rule: {},
  },
  suggestions_rejected: [
    {
      id: "s2",
      requirement_id: "r2",
      type: "add_keyword",
      scope: "job_specific",
      target_section: "skills",
      original_text: "Python",
      proposed_text: "Certified Kubernetes administrator",
      rationale: "Adds the missing tool",
      guard_status: "rejected_fabricated_specific",
      guard_reason: "kubernetes",
      decision: "pending",
      decision_reason: null,
    },
  ],
  cover_note: {
    text: "Dear hiring team, I build Python services.",
    generated: "Dear hiring team, I build Python services.",
    edited: null,
    guard_status: "pass",
    guard_reason: null,
    is_draft: true,
    word_count: 7,
  },
};

async function stubPacket(page: Page, body: unknown) {
  await page.route("**/api/analyses/a1**", (route) =>
    route.fulfill({ json: body, status: 200 }),
  );
  await page.route("**/api/jd-snapshots/s1", (route) =>
    route.fulfill({
      json: {
        id: "s1",
        job_id: "j1",
        source_kind: "page_paste",
        captured_at: "2026-11-07T09:00:00Z",
        chars: 120,
        injection_flags: [],
        truncation_warning: false,
        raw_text: "We need Python and Kubernetes.",
      },
      status: 200,
    }),
  );
  await page.route("**/api/cvs", (route) =>
    route.fulfill({
      json: {
        items: [{ id: "c1", label: "Backend", latest_version_id: "v1" }],
      },
      status: 200,
    }),
  );
  await page.route("**/api/jobs/j1/history", (route) =>
    route.fulfill({ json: { items: [] }, status: 200 }),
  );
  await page.route("**/api/jobs/j1", (route) =>
    route.fulfill({
      json: {
        id: "j1",
        title: "Backend Engineer",
        company: "Northwind",
        status: "analyzed",
        outcome: null,
        latest_snapshot_id: "s1",
        created_at: "2026-11-07T09:00:00Z",
        updated_at: "2026-11-07T09:00:00Z",
      },
      status: 200,
    }),
  );
}

test("packet: sections, sticky nav and the guard's rejections", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await stubPacket(page, PACKET);

  await page.goto("/analyses/a1");

  await expect(
    page.getByRole("heading", { level: 1, name: "Backend Engineer" }),
  ).toBeVisible();
  await expect(page.getByText("Northwind")).toBeVisible();
  // Provenance must name the model and the run count, and must never claim a
  // cache hit: every stored packet has a cache key, so that claim would be false.
  await expect(page.getByText(/3 runs per requirement/)).toBeVisible();
  await expect(page.getByText(/Reused from cache/)).toHaveCount(0);

  await expect(page.getByText(/Post is onsite/)).toBeVisible();
  // The two quiet constraints collapse into one line instead of a list.
  await expect(
    page.getByText("1 other constraint matches or is not stated in the post."),
  ).toBeVisible();

  // Guard-rejected suggestions are hidden until asked for, then explained.
  await expect(
    page.getByText("Certified Kubernetes administrator"),
  ).toHaveCount(0);
  await page.getByRole("checkbox", { name: /rejected by the guard/ }).check();
  await expect(
    page.getByText("Certified Kubernetes administrator"),
  ).toBeVisible();
  await expect(
    page.getByText(/Rejected by the fabrication guard/),
  ).toBeVisible();

  // The scroll-spy keeps the sticky nav honest without polling scroll offsets.
  await page.locator("#matches").scrollIntoViewIfNeeded();
  await expect(page.getByRole("link", { name: "Matches" })).toHaveAttribute(
    "aria-current",
    "true",
  );
  const navTop = await page
    .getByRole("navigation", { name: "Packet sections" })
    .evaluate((element) => Math.round(element.getBoundingClientRect().top));
  expect(navTop).toBe(0);

  expect(pageErrors).toEqual([]);
});

test("packet: a card that cannot show anything says so", async ({ page }) => {
  await stubPacket(page, {
    ...PACKET,
    cover_note: {
      text: null,
      generated: null,
      edited: null,
      guard_status: "no_strong_matches",
      guard_reason: null,
      is_draft: true,
      word_count: 0,
    },
  });

  await page.goto("/analyses/a1");

  await expect(
    page.getByText("No draft could be verified for this job."),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: /draft/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});
