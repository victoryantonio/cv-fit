import { Link } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { useCvs } from "@/api/cvs";
import { describeStatus, useHealth } from "@/api/health";

function StatusRow({ label, value }: { label: string; value: string }) {
  const good = value === "ok" || value === "connected";
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2 last:border-b-0">
      <dt className="text-dense text-muted">{label}</dt>
      <dd className={good ? "text-dense" : "text-dense text-partial-fg"}>
        {describeStatus(value)}
      </dd>
    </div>
  );
}

type Action = { text: string; label: string; to: string };

/**
 * Only actions this build can actually take. Jobs and packets arrive in a
 * later stage; an action that leads nowhere is worse than no action.
 */
function useNextActions(): Action[] {
  const cvs = useCvs();
  if (!cvs.isSuccess) return [];

  const actions: Action[] = [];
  if (cvs.data.length === 0) {
    actions.push({
      text: "No CV yet. Upload one so there is something to match job posts against.",
      label: "Add a CV",
      to: "/cvs",
    });
  }
  for (const cv of cvs.data) {
    if (!cv.latest_version_id) {
      actions.push({
        text: `“${cv.label}” has no file yet, so it cannot be analyzed.`,
        label: "Add the file",
        to: "/cvs",
      });
    }
  }
  return actions;
}

export function Home() {
  const health = useHealth();
  const actions = useNextActions();

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-title">Home</h1>
        <p className="text-dense text-muted">
          Runs on this machine. Job text and CV text go only to the model you
          configured.
        </p>
      </header>

      {actions.length > 0 ? (
        <section aria-labelledby="next-actions" className="space-y-2">
          <h2 id="next-actions" className="text-section">
            Next actions
          </h2>
          <ul className="space-y-2">
            {actions.map((action) => (
              <li
                key={`${action.to}-${action.text}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel px-4 py-3"
              >
                <span className="text-dense">{action.text}</span>
                <Link
                  to={action.to}
                  className="text-dense text-accent underline"
                >
                  {action.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section
        aria-labelledby="system-status"
        className="rounded-lg border border-line bg-panel p-4"
      >
        <h2 id="system-status" className="text-section">
          System status
        </h2>

        {health.isPending ? (
          <p className="mt-2 text-dense text-muted">Checking</p>
        ) : health.isError ? (
          <div className="mt-2 space-y-3">
            <p className="text-dense text-muted">
              {errorMessage(health.error)}
            </p>
            <button
              type="button"
              onClick={() => void health.refetch()}
              className="rounded-md border border-line px-3 py-1.5 text-dense hover:bg-bg"
            >
              Try again
            </button>
          </div>
        ) : (
          <dl className="mt-2">
            <StatusRow label="Database" value={health.data.database} />
            <StatusRow label="Model" value={health.data.llm} />
            <StatusRow label="Gmail" value={health.data.gmail} />
          </dl>
        )}
      </section>
    </div>
  );
}
