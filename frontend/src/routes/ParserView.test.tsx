import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ParserView } from "@/routes/ParserView";
import { jsonResponse, renderScreen, stubRoutes } from "@/test/utils";

const VIEW = {
  id: "v-1",
  cv_id: "cv-1",
  version_no: 2,
  note: "Tightened the summary",
  file_name: "cv-backend.pdf",
  file_sha256: "c".repeat(64),
  text_sha256: "d".repeat(64),
  uploaded_at: "2025-01-02T09:00:00+00:00",
  warnings: ["multi_column_suspected", "text_short"],
  sections: ["summary", "experience"],
  redaction: { EMAIL: 2, PHONE: 1, ID: 0 },
  redacted_chars: 900,
  text: "SUMMARY\n[EMAIL_1]\n\nEXPERIENCE\nBuilt things.",
  section_texts: { experience: "Built things.", summary: "SUMMARY\n[EMAIL_1]" },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Parser View", () => {
  it("explains each parser warning in words and keeps the code out of sight", async () => {
    stubRoutes({
      "/api/cv-versions/v-1/parser-view": () => jsonResponse(VIEW),
    });

    renderScreen(<ParserView />, {
      route: "/cv-versions/v-1",
      path: "/cv-versions/:versionId",
    });

    expect(
      await screen.findByText(/Looks like two columns/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Less than 300 characters/)).toBeInTheDocument();
    expect(
      screen.queryByText(/multi_column_suspected/),
    ).not.toBeInTheDocument();
  });

  it("shows the redacted text as plain text, unchanged", async () => {
    stubRoutes({
      "/api/cv-versions/v-1/parser-view": () => jsonResponse(VIEW),
    });

    renderScreen(<ParserView />, {
      route: "/cv-versions/v-1",
      path: "/cv-versions/:versionId",
    });

    const block = await screen.findByText(/Built things\./);
    expect(block.tagName).toBe("PRE");
    expect(block.textContent).toContain("[EMAIL_1]");
  });

  it("counts only the categories that matched something", async () => {
    stubRoutes({
      "/api/cv-versions/v-1/parser-view": () => jsonResponse(VIEW),
    });

    renderScreen(<ParserView />, {
      route: "/cv-versions/v-1",
      path: "/cv-versions/:versionId",
    });

    expect(await screen.findByText("Email addresses")).toBeInTheDocument();
    expect(screen.getByText("Phone numbers")).toBeInTheDocument();
    expect(screen.queryByText("ID numbers")).not.toBeInTheDocument();
  });

  it("offers a way back when the version does not exist", async () => {
    stubRoutes({
      "/api/cv-versions/gone/parser-view": () =>
        new Response(
          JSON.stringify({
            code: "NOT_FOUND",
            message: "No such version.",
            details: {},
            request_id: "r-1",
          }),
          { status: 404, headers: { "content-type": "application/json" } },
        ),
    });

    renderScreen(<ParserView />, {
      route: "/cv-versions/gone",
      path: "/cv-versions/:versionId",
    });

    expect(await screen.findByText("No such version.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to CVs" })).toHaveAttribute(
      "href",
      "/cvs",
    );
  });
});
