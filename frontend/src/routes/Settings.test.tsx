import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Settings } from "@/routes/Settings";
import { jsonResponse, renderScreen, stubRoutes } from "@/test/utils";

const STORED = {
  criteria: {
    include_keywords: ["python"],
    exclude_keywords: [],
    locations: ["Remote"],
    seniority: [],
  },
  non_negotiables: {
    languages: ["english"],
    locations: [],
    work_modes: ["remote"],
    salary_floor: null,
    work_authorization: null,
  },
  llm: {
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    runs: 3,
    temperature: 0.2,
    api_key_set: true,
  },
  budget: { monthly_tokens: null },
  redaction: { terms: [] },
};

const SUMMARY = {
  counts: {
    cv: 1,
    cv_version: 1,
    job_posting: 1,
    analysis: 0,
    app_setting: 1,
  },
  total_rows: 4,
  database: { path: "D:\\data\\app.db", files: 1, bytes: 8192 },
  uploads: { path: "D:\\data\\uploads", files: 1, bytes: 2048 },
  backups: { directory: "D:\\data\\backups", files: 0, latest: null },
};

const NOT_CONNECTED = {
  code: "GMAIL_NOT_CONNECTED",
  message: "Gmail is not connected. Run the auth command, then retry.",
  details: {
    status: "not_connected",
    command: "uv run python -m app.mcp_gmail auth",
  },
  request_id: "req-1",
};

function baseRoutes() {
  return {
    "GET /api/settings": () => jsonResponse(STORED),
    "PUT /api/settings": () => jsonResponse(STORED),
    "GET /api/data": () => jsonResponse(SUMMARY),
    "/api/health": () =>
      jsonResponse({
        status: "ok",
        database: "ok",
        gmail: "not_connected",
        llm: "ok",
        checked_at: "2025-01-02T09:00:00+00:00",
      }),
  };
}

/** The last request body for a method, parsed. */
function sentBody(method: string): Record<string, unknown> {
  const calls = vi.mocked(fetch).mock.calls;
  const match = [...calls]
    .reverse()
    .find(([, init]) => init?.method === method);
  const raw = match?.[1]?.body;
  return raw ? (JSON.parse(String(raw)) as Record<string, unknown>) : {};
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Settings", () => {
  it("opens on the criteria tab with the stored values", async () => {
    stubRoutes(baseRoutes());

    renderScreen(<Settings />);

    expect(await screen.findByLabelText("Include keywords")).toHaveValue(
      "python",
    );
    expect(screen.getByLabelText("Locations")).toHaveValue("Remote");
    expect(
      screen.getByRole("tab", { name: "Privacy and data" }),
    ).toBeInTheDocument();
  });

  it("saves the whole document, cleaned, and never sends an empty key", async () => {
    stubRoutes(baseRoutes());
    const user = userEvent.setup();

    renderScreen(<Settings />);
    const include = await screen.findByLabelText("Include keywords");
    fireEvent.change(include, { target: { value: "python, go ," } });
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sentBody("PUT")).toHaveProperty("criteria"));
    const body = sentBody("PUT");
    expect(
      (body.criteria as { include_keywords: string[] }).include_keywords,
    ).toEqual(["python", "go"]);
    // Every section travels together; a partial body would blank the rest.
    expect(body).toHaveProperty("non_negotiables");
    expect(body.llm).toHaveProperty("runs", 3);
    expect(body.llm).not.toHaveProperty("api_key");
  });

  it("refuses a base URL that is neither HTTPS nor localhost", async () => {
    stubRoutes(baseRoutes());
    const user = userEvent.setup();

    renderScreen(<Settings />);
    await user.click(await screen.findByRole("tab", { name: "Model" }));
    fireEvent.change(await screen.findByLabelText("Base URL"), {
      target: { value: "http://api.example.com/v1" },
    });

    expect(
      await screen.findByText(
        "The base URL must use HTTPS, or plain HTTP on localhost.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("names the host that receives redacted text and what is stored", async () => {
    stubRoutes(baseRoutes());
    const user = userEvent.setup();

    renderScreen(<Settings />);
    await user.click(
      await screen.findByRole("tab", { name: "Privacy and data" }),
    );

    // The provider host is named, not just "an API".
    expect(await screen.findByText("api.deepseek.com")).toBeInTheDocument();
    expect(screen.getByText("1 file, 2.0 kB")).toBeInTheDocument();
  });

  it("backs up and reports the file it wrote", async () => {
    stubRoutes({
      ...baseRoutes(),
      "POST /api/backup": () =>
        jsonResponse({
          path: "D:\\data\\backups\\app-20250102-090000.db",
          bytes: 8192,
        }),
    });
    const user = userEvent.setup();

    renderScreen(<Settings />);
    await user.click(
      await screen.findByRole("tab", { name: "Privacy and data" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Back up database" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Wrote D:\\data\\backups\\app-20250102-090000.db",
    );
  });

  it("asks for the word before deleting, then reports what went", async () => {
    stubRoutes({
      ...baseRoutes(),
      "POST /api/data/purge": () =>
        jsonResponse({
          deleted: { cv: 1, cv_version: 1, job_posting: 1 },
          uploads_deleted: 1,
        }),
    });
    const user = userEvent.setup();

    renderScreen(<Settings />);
    await user.click(
      await screen.findByRole("tab", { name: "Privacy and data" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Delete all data" }),
    );

    const dialog = await screen.findByRole("dialog");
    // Settings are kept, so they are not listed as deleted.
    expect(within(dialog).getByText("CVs")).toBeInTheDocument();
    expect(within(dialog).queryByText(/app setting/i)).not.toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", {
      name: "Delete everything",
    });
    expect(confirm).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Type DELETE to confirm"), {
      target: { value: "DELETE" },
    });
    await user.click(
      within(dialog).getByRole("button", { name: "Delete everything" }),
    );

    expect(
      await screen.findByText(
        "Database rows removed: 3. Uploaded files removed: 1.",
      ),
    ).toBeInTheDocument();
    expect(sentBody("POST")).toEqual({ confirm: "DELETE" });
  });

  it("shows the scope and the command when Gmail is not connected", async () => {
    stubRoutes({
      ...baseRoutes(),
      "POST /api/gmail/connect": () => jsonResponse(NOT_CONNECTED, 409),
    });
    const user = userEvent.setup();

    renderScreen(<Settings />);
    await user.click(await screen.findByRole("tab", { name: "Gmail" }));
    expect(await screen.findByText("gmail.readonly")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Check connection" }));

    expect(
      await screen.findByText("uv run python -m app.mcp_gmail auth"),
    ).toBeInTheDocument();
  });
});
