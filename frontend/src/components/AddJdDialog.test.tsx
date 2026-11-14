import { fireEvent, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AddJdDialog } from "@/components/AddJdDialog";
import { MAX_JD_CHARS, MIN_JD_CHARS } from "@/lib/jdFlags";
import { jsonResponse, renderScreen } from "@/test/utils";

function stubSave() {
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
      if (url !== "/api/jobs/j1/snapshots")
        throw new TypeError(`No stub for ${url}`);
      if (typeof init?.body === "string") bodies.push(init.body);
      return jsonResponse({ snapshot: { id: "s1" }, reused: false }, 201);
    }),
  );
  return bodies;
}

async function openDialog() {
  renderScreen(<AddJdDialog jobId="j1" jobTitle="Backend Engineer" />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Add JD" }));
  return user;
}

describe("AddJdDialog", () => {
  it("will not save text that is too short to judge", async () => {
    const user = await openDialog();

    await user.type(
      screen.getByLabelText("Paste the whole job page"),
      "too short",
    );

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(
      screen.getByText(new RegExp(`at least ${MIN_JD_CHARS} needed`)),
    ).toBeInTheDocument();
  });

  it("saves the pasted page text and closes", async () => {
    const bodies = stubSave();
    const user = await openDialog();

    fireEvent.change(screen.getByLabelText("Paste the whole job page"), {
      target: { value: "We are hiring a backend engineer. ".repeat(8) },
    });
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(JSON.parse(bodies[0] ?? "{}")).toMatchObject({
      source_kind: "page_paste",
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("refuses text over the limit the API enforces", async () => {
    await openDialog();

    fireEvent.change(screen.getByLabelText("Paste the whole job page"), {
      target: { value: "a".repeat(MAX_JD_CHARS + 1) },
    });

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    // The separator in a formatted number depends on the locale, so match loosely.
    expect(
      screen.getByText(/characters · over the .+ limit, so cut it down/),
    ).toBeInTheDocument();
  });
});
