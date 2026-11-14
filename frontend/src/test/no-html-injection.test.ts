import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(import.meta.dirname, "..");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

/**
 * Model output is text, and this app has no reason to ever inject markup.
 * A grep-style guard is stronger than a review habit: it fails the build.
 */
describe("markup safety", () => {
  it("never sets HTML from code or data", () => {
    const offenders = sourceFiles(SRC)
      .filter(
        (file) => !file.endsWith(".test.ts") && !file.endsWith(".test.tsx"),
      )
      .filter((file) =>
        readFileSync(file, "utf8").includes("dangerouslySetInnerHTML"),
      );
    expect(offenders).toEqual([]);
  });
});
