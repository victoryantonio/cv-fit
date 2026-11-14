import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

/**
 * Renders one screen with retries off, so a failing query fails once and fast.
 * Pass `path` for any screen that reads route params: a screen rendered without
 * a matching route sees no params at all.
 */
export function renderScreen(
  ui: ReactElement,
  { route = "/", path = "*" }: { route?: string; path?: string } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Stubs fetch per request, so a screen with more than one query can be tested.
 * A key is either a path (`/api/cvs`) or a method plus path (`POST /api/cvs`);
 * the method key wins. An unstubbed request throws, which the client reports as
 * "Cannot reach the local server."
 */
export function stubRoutes(routes: Record<string, () => Response>): void {
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
      const handler = routes[`${method} ${url}`] ?? routes[url];
      if (!handler) throw new TypeError(`No stub for ${method} ${url}`);
      return handler();
    }),
  );
}
