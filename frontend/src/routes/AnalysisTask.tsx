import { Link, Navigate, useParams } from "react-router-dom";

import { errorMessage } from "@/api/client";
import {
  isTaskDone,
  useCancelTask,
  useRetryTask,
  useTask,
} from "@/api/analysis";
import { Button } from "@/components/Button";
import { allSteps, stepLabel, taskStatusLabel } from "@/lib/packet";

function Steps({ current }: { current: string | null }) {
  const steps = allSteps();
  const index = current ? steps.indexOf(current) : -1;
  return (
    <ol aria-live="polite" className="space-y-1">
      {steps.map((step, position) => {
        const state =
          position < index ? "done" : position === index ? "current" : "later";
        return (
          <li
            key={step}
            aria-current={state === "current" ? "step" : undefined}
            className={
              state === "current"
                ? "text-dense font-medium text-ink"
                : state === "done"
                  ? "text-dense text-muted"
                  : "text-dense text-muted opacity-60"
            }
          >
            {state === "done" ? "Done · " : null}
            {stepLabel(step)}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * The run screen. Polling stops on a terminal status, and leaving the page
 * never cancels anything: the worker owns the task, this page only watches it.
 */
export function AnalysisTask() {
  const { taskId } = useParams<{ taskId: string }>();
  const id = taskId ?? "";
  const task = useTask(id);
  const retry = useRetryTask(id);
  const cancel = useCancelTask(id);

  if (task.isPending) return <p className="text-dense text-muted">Loading</p>;

  if (task.isError) {
    return (
      <div className="space-y-3">
        <h1 className="text-title">Running the analysis</h1>
        <p className="text-dense text-muted">{errorMessage(task.error)}</p>
        <Button onClick={() => void task.refetch()}>Try again</Button>
      </div>
    );
  }

  const run = task.data;
  if (run.status === "ok" && run.analysis_id) {
    return <Navigate to={`/analyses/${run.analysis_id}`} replace />;
  }

  const failed = run.status === "failed" || run.status === "cancelled";

  return (
    <div className="max-w-content space-y-5">
      <header className="space-y-1">
        <nav aria-label="Breadcrumb" className="text-caption text-muted">
          <Link to="/jobs" className="underline">
            Jobs
          </Link>{" "}
          / analysis
        </nav>
        <h1 className="text-title">Running the analysis</h1>
        <p className="text-dense text-muted">
          {taskStatusLabel(run.status)}
          {run.attempts > 1 ? ` · attempt ${run.attempts}` : ""}. You can leave
          this page; the run continues.
        </p>
      </header>

      {failed ? (
        <div
          role="alert"
          className="rounded-md border border-gap-line bg-gap-bg px-3 py-2 text-dense text-gap-fg"
        >
          <p className="font-medium">
            {run.status === "cancelled"
              ? "The run was cancelled."
              : "The run stopped before it finished."}
          </p>
          <p className="mt-1">
            {run.error_code
              ? `The server reported ${run.error_code}. Nothing was saved, so no packet exists for this job yet.`
              : "Nothing was saved, so no packet exists for this job yet."}
          </p>
        </div>
      ) : (
        <Steps current={run.current_step ?? null} />
      )}

      {retry.isError ? (
        <p role="alert" className="text-dense text-gap-fg">
          {errorMessage(retry.error)}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {failed ? (
          <Button
            variant="primary"
            busy={retry.isPending}
            onClick={() => retry.mutate()}
          >
            Retry
          </Button>
        ) : (
          <Button
            variant="ghost"
            busy={cancel.isPending}
            disabled={isTaskDone(run.status)}
            onClick={() => cancel.mutate()}
          >
            Cancel this run
          </Button>
        )}
        <Link to="/jobs" className="text-dense text-accent underline">
          Back to jobs
        </Link>
      </div>
    </div>
  );
}
