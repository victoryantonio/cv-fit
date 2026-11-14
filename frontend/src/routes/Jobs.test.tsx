import { screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { JobListItem } from "@/api/jobs";
import { Jobs } from "@/routes/Jobs";
import { jsonResponse, renderScreen, stubRoutes } from "@/test/utils";

const JOB: JobListItem = {
  id: "j1",
  title: "Backend Engineer",
  company: "Northwind",
  location: "Remote",
  url: null,
  source: "gmail_alert",
  status: "new",
  outcome: "none",
  received_at: "2026-11-07T09:12:00Z",
  created_at: "2026-11-07T09:12:00Z",
  applied_at: null,
  filter_reason: null,
  latest_snapshot_id: null,
  snapshot_count: 0,
};

function stubJobs(extra: Record<string, () => Response> = {}) {
  const calls: string[] = [];
  const bodies: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.pathname
            : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push(`${method} ${url}`);
      if (typeof init?.body === "string") bodies.push(init.body);
      const handler =
        extra[`${method} ${url}`] ??
        extra[url] ??
        (url === "/api/jobs"
          ? () => jsonResponse({ items: [JOB] })
          : url === "/api/jobs/sync-status"
            ? () =>
                jsonResponse({
                  source: "gmail",
                  synced_at: "2026-11-07T09:12:00Z",
                })
            : undefined);
      if (!handler) throw new TypeError(`No stub for ${method} ${url}`);
      return handler();
    }),
  );
  return { calls, bodies };
}

describe("Jobs", () => {
  it("lists a job with where it is and says the text is missing", async () => {
    stubJobs();
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    expect(
      await screen.findByRole("link", { name: "Backend Engineer" }),
    ).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByText("Northwind · Remote")).toBeInTheDocument();
    expect(screen.getByText("Add JD to analyze")).toBeInTheDocument();
    expect(await screen.findByText(/Last sync/)).toBeInTheDocument();
  });

  it("dismisses a job through the API", async () => {
    const { calls } = stubJobs({
      "PATCH /api/jobs/j1": () => jsonResponse({ ...JOB, status: "dismissed" }),
    });
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(calls).toContain("PATCH /api/jobs/j1"));
  });

  it("offers to keep a pre-filtered job", async () => {
    const { bodies } = stubJobs({
      "GET /api/jobs": () =>
        jsonResponse({ items: [{ ...JOB, filter_reason: "senior_title" }] }),
      "PATCH /api/jobs/j1": () => jsonResponse({ ...JOB, filter_reason: null }),
    });
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    expect(
      await screen.findByText(/Filtered by: senior_title/),
    ).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Show anyway" }));

    await waitFor(() =>
      expect(bodies).toContain(JSON.stringify({ keep: true })),
    );
  });

  it("asks the server for the chosen status", async () => {
    const { calls } = stubJobs({
      "GET /api/jobs?status=dismissed": () => jsonResponse({ items: [] }),
    });
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Status"),
      "dismissed",
    );

    await waitFor(() =>
      expect(calls).toContain("GET /api/jobs?status=dismissed"),
    );
  });

  it("says so when there is nothing yet", async () => {
    stubJobs({ "GET /api/jobs": () => jsonResponse({ items: [] }) });
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    expect(await screen.findByText(/No jobs yet/)).toBeInTheDocument();
  });

  it("reports an unreachable server and offers to retry", async () => {
    stubRoutes({});
    renderScreen(<Jobs />, { route: "/jobs", path: "/jobs" });

    expect(
      await screen.findByText("Cannot reach the local server."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
});
