import { useState } from "react";

import { errorMessage } from "@/api/client";
import { useJobs, type JobFilters } from "@/api/jobs";
import { Button } from "@/components/Button";
import { JobRow } from "@/components/jobs/JobRow";
import { SyncPanel } from "@/components/jobs/SyncPanel";
import { ANY, JobsToolbar } from "@/components/jobs/Toolbar";
import { NewJobDialog } from "@/components/NewJobDialog";
import { count } from "@/lib/format";

export function Jobs() {
  const [status, setStatus] = useState(ANY);
  const [filtered, setFiltered] = useState(ANY);

  const filters: JobFilters = {
    status: status === ANY ? undefined : status,
    filtered: filtered === ANY ? undefined : filtered === "filtered",
  };
  const jobs = useJobs(filters);
  const isFiltered = status !== ANY || filtered !== ANY;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-title">Jobs</h1>
        <p className="text-dense text-muted">
          Open the job post, expand the description, select all, copy, then use
          Add JD. Nothing is fetched from the site for you.
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <JobsToolbar
          status={status}
          filtered={filtered}
          onStatus={setStatus}
          onFiltered={setFiltered}
        />
        <div className="flex flex-wrap items-center gap-3">
          <SyncPanel />
          <NewJobDialog />
        </div>
      </div>

      {jobs.isPending ? (
        <p className="text-dense text-muted">Loading</p>
      ) : jobs.isError ? (
        <div className="space-y-3">
          <p className="text-dense text-muted">{errorMessage(jobs.error)}</p>
          <Button onClick={() => void jobs.refetch()}>Try again</Button>
        </div>
      ) : jobs.data.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-dense text-muted">
          {isFiltered
            ? "No jobs match these filters."
            : "No jobs yet. Add one yourself, or sync alerts once Gmail is connected."}
        </p>
      ) : (
        <table className="w-full border-collapse text-left">
          <caption className="pb-2 text-left text-caption text-muted">
            {count(jobs.data.length, "job")}
          </caption>
          <thead>
            <tr className="border-b border-line text-caption text-muted">
              <th scope="col" className="py-2 pr-3 font-medium">
                Job
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Received
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Status
              </th>
              <th scope="col" className="py-2 font-medium">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
