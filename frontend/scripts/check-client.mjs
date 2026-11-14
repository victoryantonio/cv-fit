#!/usr/bin/env node
/**
 * Fails when the committed TS client no longer matches openapi.json.
 *
 * The spec itself is regenerated from the backend (python -m app.cli openapi),
 * and a pytest contract test asserts that file equals create_app().openapi().
 * Together they close the loop: backend change -> stale client -> red build.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const committed = join(root, "src", "api", "schema.d.ts");
const cli = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");
const workdir = mkdtempSync(join(tmpdir(), "cv-fit-client-"));
const generated = join(workdir, "schema.d.ts");

try {
  // Spawned as `node cli.js`, not `npx`, so no shell quoting is involved.
  execFileSync(
    process.execPath,
    [cli, join(root, "openapi.json"), "--output", generated],
    { cwd: root, stdio: "inherit" },
  );
  const fresh = readFileSync(generated, "utf8");
  const current = readFileSync(committed, "utf8");
  if (fresh !== current) {
    console.error("src/api/schema.d.ts is stale.");
    console.error("Run: python -m app.cli openapi && npm run gen:api");
    process.exit(1);
  }
  console.log("API client matches openapi.json.");
} finally {
  rmSync(workdir, { recursive: true, force: true });
}
