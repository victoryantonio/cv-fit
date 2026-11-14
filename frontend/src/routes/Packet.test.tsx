import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Analysis, Suggestion } from "@/api/analysis";
import { RunAnalysisDialog } from "@/components/RunAnalysisDialog";
import { AnalysisTask } from "@/routes/AnalysisTask";
import { Packet } from "@/routes/Packet";
import { jsonResponse, renderScreen } from "@/test/utils";

const SUGGESTION: Suggestion = {
  id: "s1",
  requirement_id: "r1",
  type: "reword",
  scope: "job_specific",
  target_section: "experience",
  original_text: "Built Python services",
  proposed_text: "Built Python services for two teams",
  rationale: "Matches the wording of the post",
  guard_status: "pass",
  guard_reason: null,
  decision: "pending",
  decision_reason: null,
};

const BLOCKED: Suggestion = {
  ...SUGGESTION,
  id: "s2",
  type: "add_keyword",
  proposed_text: "Certified Kubernetes administrator",
  guard_status: "rejected_fabricated_specific",
  guard_reason: "kubernetes",
};

const PACKET: Analysis = {
  id: "a1",
  status: "ok",
  model: "deepseek-v4-flash",
  prompt_bundle: "match.v3",
  match_runs: 3,
  cache_key: null,
  created_at: "2026-11-07T10:00:00Z",
  cv_version_id: "v1",
  extraction_id: "x1",
  snapshot_id: null,
  job_id: null,
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
    {
      id: "r3",
      position: 3,
      text: "Team mentoring",
      importance: "nice",
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
      votes: { gap: 2, partial: 1 },
      agreement: 0.67,
      flags: ["unstable"],
    },
    {
      requirement_id: "r3",
      verdict: "partial",
      evidence_quote: "Mentored two juniors",
      rationale: null,
      votes: { partial: 3 },
      agreement: 1,
      flags: [],
    },
  ],
  summary: {
    label: "stretch",
    coverage: 42,
    counts: { strong: 1, partial: 1, gap: 1 },
    must_have: { met: 1, total: 2, coverage: 50 },
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
    unstable_count: 1,
    constraint_flags: [
      {
        kind: "work_mode",
        status: "conflict",
        note: "Post is onsite",
        jd_value: "onsite",
        user_value: "remote",
      },
    ],
  },
  suggestions: [SUGGESTION],
  suggestion_provenance: {
    total: 2,
    visible: 1,
    hidden: 1,
    rejected_by_rule: {},
  },
  suggestions_rejected: [BLOCKED],
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

/** The packet screen reads its query string, so stub by prefix rather than exact URL. */
function stubPacket(body: Analysis) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.pathname
            : input.url;
      calls.push(url);
      if (url.startsWith("/api/analyses/a1")) return jsonResponse(body);
      throw new TypeError(`No stub for ${url}`);
    }),
  );
  return calls;
}

describe("Packet", () => {
  it("reports the verdict, the counts and the flags the server computed", async () => {
    stubPacket(PACKET);
    renderScreen(<Packet />, {
      route: "/analyses/a1",
      path: "/analyses/:analysisId",
    });

    expect(await screen.findByText("Stretch")).toBeInTheDocument();
    expect(
      screen.getByText(/Strong 1 · Partial 1 · Gap 1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Must-haves: 1 of 2 covered/)).toBeInTheDocument();
    expect(screen.getByText(/1 knockout gap/)).toBeInTheDocument();
    expect(screen.getByText(/runs that disagreed/)).toBeInTheDocument();
    expect(screen.getByText(/Post is onsite/)).toBeInTheDocument();
    expect(screen.getByText(/3 runs per requirement/)).toBeInTheDocument();
  });

  it("keeps strong matches apart from gaps and explains an unstable verdict", async () => {
    stubPacket(PACKET);
    renderScreen(<Packet />, {
      route: "/analyses/a1",
      path: "/analyses/:analysisId",
    });

    expect(
      await screen.findByRole("heading", { name: "What matches (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "What does not match (2)" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Built Python services").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/repeated runs disagreed/)).toBeInTheDocument();
  });

  it("hides the suggestions the guard rejected until the reader asks", async () => {
    stubPacket(PACKET);
    renderScreen(<Packet />, {
      route: "/analyses/a1",
      path: "/analyses/:analysisId",
    });

    expect(
      await screen.findByRole("heading", { name: "CV suggestions (2)" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Certified Kubernetes administrator/),
    ).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByLabelText(/Show 1 rejected by the guard/),
    );

    expect(
      screen.getByText(/Certified Kubernetes administrator/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Rejected by the fabrication guard/),
    ).toBeInTheDocument();
  });

  it("says no draft could be verified instead of showing an empty box", async () => {
    stubPacket({
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
    renderScreen(<Packet />, {
      route: "/analyses/a1",
      path: "/analyses/:analysisId",
    });

    expect(
      await screen.findByText(/No draft could be verified/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No requirement had verified evidence/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("The draft")).not.toBeInTheDocument();
  });

  it("labels a verified cover note as a draft and shows its word count", async () => {
    stubPacket(PACKET);
    renderScreen(<Packet />, {
      route: "/analyses/a1",
      path: "/analyses/:analysisId",
    });

    expect(
      await screen.findByText("Draft. Review before sending."),
    ).toBeInTheDocument();
    expect(screen.getByText(/7 words/)).toBeInTheDocument();
  });
});

describe("starting a run", () => {
  /** Two routes, so a navigating dialog can be followed to its destination. */
  function renderDialog(): ReactElement {
    return (
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={["/jobs"]}>
          <Routes>
            <Route
              path="/jobs"
              element={
                <RunAnalysisDialog
                  jobTitle="Backend Engineer"
                  snapshotId="s1"
                />
              }
            />
            <Route path="/tasks/:taskId" element={<AnalysisTask />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it("follows a queued run to its progress screen", async () => {
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
        if (method === "GET" && url === "/api/cvs")
          return jsonResponse({
            items: [{ id: "c1", label: "Main CV", latest_version_id: "v1" }],
          });
        if (method === "POST" && url === "/api/analyses")
          return jsonResponse(
            {
              task: { id: "t1", status: "queued", kind: "analysis" },
              cache_key: "k",
            },
            202,
          );
        if (method === "GET" && url === "/api/tasks/t1")
          return jsonResponse({
            id: "t1",
            kind: "analysis",
            status: "running",
            current_step: "s2_match",
          });
        throw new TypeError(`No stub for ${method} ${url}`);
      }),
    );

    render(renderDialog());
    const [open] = await screen.findAllByRole("button", {
      name: "Run analysis",
    });
    if (!open) throw new Error("Run analysis trigger not found");
    await userEvent.click(open);
    // Scope to the dialog: the trigger shares the same label and goes inert once it opens.
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Run analysis" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Running the analysis" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText(/Comparing each requirement with the CV/),
      ).toBeInTheDocument(),
    );
  });
});
