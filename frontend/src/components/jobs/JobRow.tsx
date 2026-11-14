import { Link } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { statusLabel, usePatchJob, type JobListItem } from "@/api/jobs";
import { AddJdDialog } from "@/components/AddJdDialog";
import { Button } from "@/components/Button";
import { RunAnalysisDialog } from "@/components/RunAnalysisDialog";
import { count, formatDateTime } from "@/lib/format";

export function JobRow({ job }: { job: JobListItem }) {
  const patch = usePatchJob(job.id);

  return (
    <tr className="border-b border-line align-top last:border-b-0">
      <td className="py-3 pr-3">
        <Link
          to={`/jobs/${job.id}`}
          className="text-dense font-medium text-accent underline"
        >
          {job.title}
        </Link>
        <p className="text-caption text-muted">
          {[job.company, job.location].filter(Boolean).join(" · ") ||
            "No company or location"}
        </p>
        {job.filter_reason ? (
          <p className="mt-1 text-caption text-partial-fg">
            Filtered by: {job.filter_reason}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => patch.mutate({ keep: true })}
            >
              Show anyway
            </button>
          </p>
        ) : null}
        <p className="mt-1 text-caption text-muted">
          {job.snapshot_count === 0
            ? "Add JD to analyze"
            : `${count(job.snapshot_count, "job text")} stored`}
        </p>
      </td>
      <td className="py-3 pr-3 text-caption text-muted">
        {formatDateTime(job.received_at ?? job.created_at)}
      </td>
      <td className="py-3 pr-3 text-dense">{statusLabel(job.status)}</td>
      <td className="py-3">
        <div className="flex flex-wrap items-center gap-2">
          <AddJdDialog jobId={job.id} jobTitle={job.title} />
          {job.latest_snapshot_id ? (
            <RunAnalysisDialog
              jobTitle={job.title}
              snapshotId={job.latest_snapshot_id}
            />
          ) : null}
          {job.status === "dismissed" ? (
            <Button onClick={() => patch.mutate({ status: "new" })}>
              Restore
            </Button>
          ) : (
            <>
              <Button onClick={() => patch.mutate({ status: "shortlisted" })}>
                Shortlist
              </Button>
              <Button
                variant="ghost"
                onClick={() => patch.mutate({ status: "dismissed" })}
              >
                Dismiss
              </Button>
            </>
          )}
        </div>
        {patch.isError ? (
          <p role="alert" className="mt-1 text-caption text-gap-fg">
            {errorMessage(patch.error)}
          </p>
        ) : null}
      </td>
    </tr>
  );
}
