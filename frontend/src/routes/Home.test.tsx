import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Home } from "@/routes/Home";
import { jsonResponse, renderScreen, stubRoutes } from "@/test/utils";

const HEALTHY = {
  status: "ok",
  database: "ok",
  gmail: "not_connected",
  llm: "ok",
  checked_at: "2025-01-02T09:00:00+00:00",
};

const NO_CVS = { items: [], total: 0 };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Home", () => {
  it("renders the three status rows in words, not codes", async () => {
    stubRoutes({
      "/api/health": () => jsonResponse(HEALTHY),
      "/api/cvs": () => jsonResponse(NO_CVS),
    });

    renderScreen(<Home />);

    expect(await screen.findByText("Database")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Gmail")).toBeInTheDocument();
    expect(screen.getAllByText("Connected")).toHaveLength(2);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
  });

  it("points at the CV screen when there is no CV yet", async () => {
    stubRoutes({
      "/api/health": () => jsonResponse(HEALTHY),
      "/api/cvs": () => jsonResponse(NO_CVS),
    });

    renderScreen(<Home />);

    expect(
      await screen.findByRole("link", { name: "Add a CV" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a CV" })).toHaveAttribute(
      "href",
      "/cvs",
    );
  });

  it("does not offer an action it cannot complete", async () => {
    stubRoutes({
      "/api/health": () => jsonResponse(HEALTHY),
      "/api/cvs": () =>
        jsonResponse({
          items: [
            {
              id: "cv-1",
              label: "Backend CV",
              created_at: "2025-01-02T09:00:00+00:00",
              version_count: 1,
              latest_version_id: "v-1",
            },
          ],
          total: 1,
        }),
    });

    renderScreen(<Home />);

    expect(await screen.findByText("Database")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Next actions" }),
    ).not.toBeInTheDocument();
  });

  it("degrades to a retry when the server is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("connection refused");
      }),
    );

    renderScreen(<Home />);

    expect(
      await screen.findByText("Cannot reach the local server."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
});
