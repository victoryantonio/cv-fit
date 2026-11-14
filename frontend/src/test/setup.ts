import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// globals are off, so Testing Library cannot register its own cleanup: without
// this every render would stack up in the same document.
afterEach(() => {
  cleanup();
});
