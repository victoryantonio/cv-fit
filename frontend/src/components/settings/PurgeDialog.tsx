/**
 * Purge is irreversible, so the dialog names every table it will empty and
 * makes the user type the word. No counts are guessed: they come from
 * `GET /api/data`, the same source the purge itself walks.
 */
import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import { PURGE_CONFIRMATION, usePurge, type DataSummary } from "@/api/data";
import { Button } from "@/components/Button";
import { errorMessage } from "@/api/client";

const TABLE_LABELS: Record<string, string> = {
  cv: "CVs",
  cv_version: "CV versions",
  job_posting: "Job posts",
  jd_snapshot: "Stored job descriptions",
  job_sync_state: "Gmail sync cursors",
  analysis: "Analyses",
  jd_extraction: "Extracted requirements",
  jd_requirement: "Requirements",
  requirement_match: "Requirement matches",
  suggestion: "Suggestions",
  analysis_task: "Background jobs",
  llm_call: "Model calls",
};

function label(table: string): string {
  return TABLE_LABELS[table] ?? table.replace(/_/g, " ");
}

/** Settings survive a purge, so listing them as deleted would be a lie. */
const KEPT: ReadonlySet<string> = new Set(["app_setting"]);

function CountRows({ counts }: { counts: Record<string, number> }) {
  const rows = Object.entries(counts).filter(
    ([table, count]) => count > 0 && !KEPT.has(table),
  );
  if (rows.length === 0) {
    return <p className="text-dense text-muted">Nothing stored yet.</p>;
  }
  return (
    <ul className="divide-y divide-line rounded-sm border border-line">
      {rows.map(([table, count]) => (
        <li key={table} className="flex justify-between px-3 py-1.5 text-dense">
          <span>{label(table)}</span>
          <span className="tabular-nums">{count}</span>
        </li>
      ))}
    </ul>
  );
}

export function PurgeDialog({
  open,
  onOpenChange,
  summary,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary?: DataSummary;
}) {
  const purge = usePurge();
  const [typed, setTyped] = useState("");
  const matches = typed.trim() === PURGE_CONFIRMATION;
  // Counted from the response, not from the summary: the summary refetches to
  // zero as soon as the purge succeeds.
  const removed = purge.data
    ? Object.values(purge.data.deleted).reduce((total, n) => total + n, 0)
    : 0;

  // Closing clears both the typed word and the previous result, so the next
  // open starts from "nothing has happened yet". A reset in an effect would
  // re-run on every render, because the mutation object is rebuilt each time.
  function handleOpenChange(next: boolean) {
    if (!next) {
      setTyped("");
      purge.reset();
    }
    onOpenChange(next);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-[min(32rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-md border border-line bg-panel p-5 shadow-lg">
          <Dialog.Title className="text-section">
            {purge.data ? "Deleted" : "Delete everything"}
          </Dialog.Title>
          <div className="mt-3 space-y-3">
            {purge.data ? (
              <>
                <p className="text-dense">
                  Database rows removed: {removed}. Uploaded files removed:{" "}
                  {purge.data.uploads_deleted}.
                </p>
                <CountRows counts={purge.data.deleted} />
                <p className="text-dense text-muted">
                  Settings and non-negotiables were kept, so the app still knows
                  your model and your limits.
                </p>
              </>
            ) : (
              <>
                <Dialog.Description className="text-dense">
                  This empties every table below and the uploads folder. There
                  is no undo; take a backup first if you might want any of it
                  back.
                </Dialog.Description>
                <CountRows counts={summary?.counts ?? {}} />
                <p className="text-caption text-muted">
                  Settings and non-negotiables are kept. The CV files you
                  uploaded are removed.
                </p>
                <div>
                  <label
                    htmlFor="purge-confirm"
                    className="block text-dense font-medium"
                  >
                    Type {PURGE_CONFIRMATION} to confirm
                  </label>
                  <input
                    id="purge-confirm"
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    autoComplete="off"
                    className="mt-1 w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
                  />
                </div>
                {purge.isError ? (
                  <p role="alert" className="text-dense text-danger">
                    {errorMessage(purge.error)}
                  </p>
                ) : null}
              </>
            )}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="ghost">{purge.data ? "Close" : "Cancel"}</Button>
            </Dialog.Close>
            {purge.data ? null : (
              <Button
                variant="primary"
                busy={purge.isPending}
                disabled={!matches}
                onClick={() => purge.mutate(PURGE_CONFIRMATION)}
              >
                Delete everything
              </Button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
