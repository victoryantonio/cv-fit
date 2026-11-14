/**
 * "Deleting is real": this shows what is stored, then offers the four honest
 * exits — a copy out, a file backup, and an empty database.
 */
import { useState } from "react";

import { errorMessage } from "@/api/client";
import { useBackup, useDataSummary } from "@/api/data";
import { Button } from "@/components/Button";
import { PurgeDialog } from "@/components/settings/PurgeDialog";

function bytes(count: number): string {
  if (count < 1024) return `${count} B`;
  if (count < 1024 * 1024) return `${(count / 1024).toFixed(1)} kB`;
  return `${(count / (1024 * 1024)).toFixed(1)} MB`;
}

function files(count: number): string {
  return count === 1 ? "1 file" : `${count} files`;
}

export function DataControls() {
  const summary = useDataSummary();
  const backup = useBackup();
  const [purging, setPurging] = useState(false);

  if (summary.isPending) {
    return <p className="text-dense text-muted">Reading what is stored...</p>;
  }
  if (summary.isError) {
    return (
      <p className="text-dense text-danger">{errorMessage(summary.error)}</p>
    );
  }

  const data = summary.data;

  return (
    <div className="space-y-4">
      <dl className="grid gap-2 text-dense sm:grid-cols-2">
        <div className="rounded-sm border border-line px-3 py-2">
          <dt className="text-caption text-muted">Database</dt>
          <dd>
            {data.total_rows} rows, {bytes(data.database.bytes)}
          </dd>
        </div>
        <div className="rounded-sm border border-line px-3 py-2">
          <dt className="text-caption text-muted">Uploads</dt>
          <dd>
            {files(data.uploads.files)}, {bytes(data.uploads.bytes)}
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        <a
          href="/api/data/export"
          download="cv-fit-export.json"
          className="inline-flex items-center rounded-sm border border-line px-3 py-1.5 text-dense hover:bg-bg"
        >
          Export JSON
        </a>
        <Button
          variant="ghost"
          busy={backup.isPending}
          onClick={() => backup.mutate()}
        >
          Back up database
        </Button>
        <Button variant="ghost" onClick={() => setPurging(true)}>
          Delete all data
        </Button>
      </div>

      <p className="text-caption text-muted">
        The export is your own text, so treat the file like the CV itself. The
        backup is a copy of the database in {data.backups.directory}.
        {data.backups.latest
          ? ` Latest: ${data.backups.latest}.`
          : " No backup yet."}
      </p>

      {backup.isError ? (
        <p role="alert" className="text-dense text-danger">
          {errorMessage(backup.error)}
        </p>
      ) : null}
      {backup.data ? (
        <p role="status" className="text-dense">
          Wrote {backup.data.path} ({bytes(backup.data.bytes)}).
        </p>
      ) : null}

      <PurgeDialog open={purging} onOpenChange={setPurging} summary={data} />
    </div>
  );
}
