import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cvs } from "@/routes/Cvs";
import { jsonResponse, renderScreen, stubRoutes } from "@/test/utils";

const ONE_CV = {
  items: [
    {
      id: "cv-1",
      label: "Backend CV",
      target_role: "Backend engineer",
      created_at: "2025-01-02T09:00:00+00:00",
      version_count: 2,
      latest_version_id: "v-2",
    },
  ],
  total: 1,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Cvs", () => {
  it("asks for a first CV when the list is empty", async () => {
    stubRoutes({ "/api/cvs": () => jsonResponse({ items: [], total: 0 }) });

    renderScreen(<Cvs />);

    expect(
      await screen.findByText(
        "No CVs yet. Use the form above to add your first one.",
      ),
    ).toBeInTheDocument();
  });

  it("lists a CV with its version count and a link to the latest version", async () => {
    stubRoutes({ "/api/cvs": () => jsonResponse(ONE_CV) });

    renderScreen(<Cvs />);

    expect(
      await screen.findByRole("heading", { name: "Backend CV" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 versions/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open latest version" }),
    ).toHaveAttribute("href", "/cv-versions/v-2");
  });

  it("turns a duplicate upload into a link to the version that already exists", async () => {
    stubRoutes({
      "/api/cvs": () => jsonResponse(ONE_CV),
      "/api/cvs/cv-1/versions": () =>
        new Response(
          JSON.stringify({
            code: "CONFLICT",
            message: "This file is already version 2.",
            details: {
              version_id: "v-2",
              version_no: 2,
              href: "/api/cv-versions/v-2",
            },
            request_id: "r-1",
          }),
          { status: 409, headers: { "content-type": "application/json" } },
        ),
    });

    renderScreen(<Cvs />);

    const input = await screen.findByLabelText(/^Add a version/);
    const file = new File(["same bytes"], "cv.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "already version 2",
    );
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: "Open that version" }),
      ).toHaveAttribute("href", "/cv-versions/v-2");
    });
  });

  it("confirms a CV created without a file and says what to do next", async () => {
    stubRoutes({
      "/api/cvs": () => jsonResponse({ items: [], total: 0 }),
      "POST /api/cvs": () =>
        jsonResponse({ id: "cv-9", label: "Data CV", target_role: null }, 201),
    });

    renderScreen(<Cvs />);

    fireEvent.change(await screen.findByLabelText("Label"), {
      target: { value: "Data CV" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add CV" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      '"Data CV" created. Add a file to it below.',
    );
  });

  it("never hides a created CV behind a failed upload", async () => {
    stubRoutes({
      "/api/cvs": () => jsonResponse({ items: [], total: 0 }),
      "POST /api/cvs": () =>
        jsonResponse({ id: "cv-9", label: "Data CV", target_role: null }, 201),
      "POST /api/cvs/cv-9/versions": () =>
        new Response(
          JSON.stringify({
            code: "VALIDATION_ERROR",
            message: "Only PDF and DOCX files are accepted.",
            details: {},
            request_id: "r-2",
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
    });

    renderScreen(<Cvs />);

    fireEvent.change(await screen.findByLabelText("Label"), {
      target: { value: "Data CV" },
    });
    const fileInput = screen.getByLabelText(/^Choose the CV file/);
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "cv.txt", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add CV" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      '"Data CV" was created, but the file was not stored',
    );
    expect(alert).toHaveTextContent("Only PDF and DOCX files are accepted.");
  });
});
