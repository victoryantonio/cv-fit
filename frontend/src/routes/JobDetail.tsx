import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { statusLabel, useJob, usePatchJob, useSnapshot } from "@/api/jobs";
import { AddJdDialog } from "@/components/AddJdDialog";
import { Button } from "@/components/Button";
import { RunAnalysisDialog } from "@/components/RunAnalysisDialog";
import { count, formatDateTime } from "@/lib/format";
import {
  explainInjection,
  explainTruncation,
  sourceKindLabel,
} from "@/lib/jdFlags";

type FlagsProps = {
  injection: string[];
  truncation: boolean;
  reasons: string[];
};

function Flags({ injection, truncation, reasons }: FlagsProps) {
  if (injection.length === 0 && !truncation) return null;
  return (
    <div className="space-y-2">
      {truncation ? (
        <div className="rounded-md border border-partial-line bg-partial-bg px-3 py-2 text-dense text-partial-fg">
          <p className="font-medium">This looks cut off.</p>
          <ul className="mt-1 space-y-1">
            {reasons.map((reason) => (
              <li key={reason}>{explainTruncation(reason)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {injection.length > 0 ? (
        <div className="rounded-md border border-line bg-panel px-3 py-2 text-dense">
          <p className="font-medium">
            This text contains instruction-like phrases. It is read as data,
            never followed.
          </p>
          <ul className="mt-1 space-y-1 text-muted">
            {injection.map((flag) => (
              <li key={flag}>{explainInjection(flag)}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const job = useJob(jobId);
  const patch = usePatchJob(jobId ?? "");

  const snapshots = job.data?.snapshots ?? [];
  // The API returns snapshots newest first, but picking by timestamp keeps this
  // right even if that order ever changes.
  const latest = snapshots.reduce<(typeof snapshots)[number] | undefined>(
    (newest, item) =>
      !newest || item.captured_at > newest.captured_at ? item : newest,
    undefined,
  );
  const snapshot = useSnapshot(latest?.id);

  if (job.isPending) {
    return <p className="text-dense text-muted">Loading</p>;
  }

  if (job.isError) {
    return (
      <div className="space-y-3">
        <h1 className="text-title">Job</h1>
        <p className="text-dense text-muted">{errorMessage(job.error)}</p>
        <div className="flex items-center gap-3">
          <Button onClick={() => void job.refetch()}>Try again</Button>
          <Link to="/jobs" className="text-dense text-accent underline">
            Back to jobs
          </Link>
        </div>
      </div>
    );
  }

  const detail = job.data;
  const where = [detail.company, detail.location].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <nav aria-label="Breadcrumb" className="text-caption text-muted">
          <Link to="/jobs" className="underline">
            Jobs
          </Link>{" "}
          / {statusLabel(detail.status)}
        </nav>
        <h1 className="text-title">{detail.title}</h1>
        <p className="text-dense text-muted">
          {where || "No company or location"} ·{" "}
          {detail.received_at
            ? `received ${formatDateTime(detail.received_at)}`
            : `added ${formatDateTime(detail.created_at)}`}
        </p>
        {detail.url ? (
          <p className="text-caption">
            {/* A link the user clicks themselves: the app never fetches this. */}
            <a
              href={detail.url}
              className="text-accent underline"
              rel="noreferrer noopener"
            >
              Open the original post
            </a>
          </p>
        ) : null}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <AddJdDialog jobId={detail.id} jobTitle={detail.title} />
        {latest ? (
          <RunAnalysisDialog jobTitle={detail.title} snapshotId={latest.id} />
        ) : null}
        <Button onClick={() => patch.mutate({ status: "shortlisted" })}>
          Shortlist
        </Button>
        <Button
          variant="ghost"
          onClick={() => patch.mutate({ status: "dismissed" })}
        >
          Dismiss
        </Button>
      </div>
      {patch.isError ? (
        <p role="alert" className="text-dense text-gap-fg">
          {errorMessage(patch.error)}
        </p>
      ) : null}

      <section aria-labelledby="jd-text" className="space-y-3">
        <h2 id="jd-text" className="text-section">
          Job text
        </h2>

        {snapshots.length === 0 ? (
          <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-dense text-muted">
            No job text yet. Copy the post and use Add JD; analysis only reads
            text you pasted.
          </p>
        ) : (
          <>
            <p className="text-caption text-muted">
              Showing the newest of {count(snapshots.length, "stored text")}
              {latest ? ` · ${sourceKindLabel(latest.source_kind)}` : ""}
              {latest ? ` · ${latest.chars.toLocaleString()} characters` : ""}
            </p>

            {snapshot.isPending ? (
              <p className="text-dense text-muted">Loading</p>
            ) : snapshot.isError ? (
              <p className="text-dense text-muted">
                {errorMessage(snapshot.error)}
              </p>
            ) : (
              <>
                <Flags
                  injection={snapshot.data.injection_flags}
                  truncation={snapshot.data.truncation_warning}
                  reasons={snapshot.data.truncation_reasons}
                />
                <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-panel p-3 font-mono text-quote text-ink">
                  {snapshot.data.raw_text}
                </pre>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
