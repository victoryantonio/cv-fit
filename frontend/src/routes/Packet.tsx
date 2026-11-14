import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { useAnalysis, useHistory, type Analysis } from "@/api/analysis";
import { useCvs } from "@/api/cvs";
import { useJob, useSnapshot } from "@/api/jobs";
import { PacketCoverNote } from "@/components/packet/PacketCoverNote";
import { PacketMatches } from "@/components/packet/PacketMatches";
import { PacketSuggestions } from "@/components/packet/PacketSuggestions";
import { PacketSummary } from "@/components/packet/PacketSummary";
import { count, formatDate, formatDateTime } from "@/lib/format";
import { fitLabel } from "@/lib/packet";
import { useActiveSection } from "@/lib/useActiveSection";

const SECTIONS = [
  { id: "summary", label: "Summary" },
  { id: "matches", label: "Matches" },
  { id: "suggestions", label: "Suggestions" },
  { id: "cover", label: "Cover note" },
  { id: "jobtext", label: "Job as read" },
] as const;

function Provenance({
  model,
  bundle,
  runs,
  createdAt,
}: {
  model: string;
  bundle: string;
  runs: number;
  createdAt: string;
}) {
  return (
    <p className="text-caption text-muted">
      {model} · prompts <span title={bundle}>{bundle.slice(0, 12)}</span> ·{" "}
      {runs === 1 ? "1 run" : `${runs} runs`} per requirement ·{" "}
      {formatDateTime(createdAt)}
    </p>
  );
}

/** Section links double as progress dots: the reader always knows where they are. */
function SectionNav({ active }: { active: string | null }) {
  return (
    <nav
      aria-label="Packet sections"
      className="sticky top-0 z-10 -mx-4 border-b border-line bg-bg px-4 py-2"
    >
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {SECTIONS.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              aria-current={active === section.id ? "true" : undefined}
              className={
                active === section.id
                  ? "text-dense font-medium text-accent underline"
                  : "text-dense text-muted hover:text-ink"
              }
            >
              {section.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SnapshotText({
  snapshotId,
}: {
  snapshotId: string | null | undefined;
}) {
  const snapshot = useSnapshot(snapshotId ?? undefined);
  if (!snapshotId)
    return <p className="text-dense text-muted">No job text is linked.</p>;
  if (snapshot.isPending)
    return <p className="text-dense text-muted">Loading</p>;
  if (snapshot.isError)
    return (
      <p role="alert" className="text-dense text-gap-fg">
        {errorMessage(snapshot.error)}
      </p>
    );
  return (
    <>
      <p className="text-caption text-muted">
        {snapshot.data.chars.toLocaleString()} characters, pasted as text
      </p>
      <pre className="mt-2 whitespace-pre-wrap break-words rounded-md border border-line bg-panel p-3 font-mono text-quote text-ink">
        {snapshot.data.raw_text}
      </pre>
    </>
  );
}

function JobHistory({
  jobId,
  cvVersionId,
}: {
  jobId: string;
  cvVersionId: string;
}) {
  const history = useHistory(jobId);
  const cvs = useCvs();
  const cv = (cvs.data ?? []).find(
    (item) => item.latest_version_id === cvVersionId,
  );
  const items = history.data?.items ?? [];

  return (
    <section aria-labelledby="history-heading" className="space-y-2">
      <h2 id="history-heading" className="text-section">
        Other analyses of this job
      </h2>
      <p className="text-dense text-muted">
        {cv ? `This packet used the latest version of ${cv.label}. ` : ""}
        {items.length === 0
          ? "No other analysis exists for this job yet."
          : `This job has ${count(items.length, "analysis", "analyses")}.`}
      </p>
      {items.length > 1 ? (
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item.analysis_id} className="text-dense">
              <Link
                to={`/analyses/${item.analysis_id}`}
                className="text-accent underline"
              >
                {formatDate(item.created_at)}
              </Link>{" "}
              · {fitLabel(item.summary.label)} · coverage{" "}
              {item.summary.coverage}% ·{" "}
              {item.comparable
                ? "comparable"
                : "different model or prompts, so not comparable"}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function Packet() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const analysis = useAnalysis(analysisId ?? "");

  if (analysis.isPending)
    return <p className="text-dense text-muted">Loading</p>;
  if (analysis.isError)
    return (
      <div className="space-y-3">
        <p role="alert" className="text-dense text-gap-fg">
          {errorMessage(analysis.error)}
        </p>
        <Link to="/jobs" className="text-dense text-accent underline">
          Back to jobs
        </Link>
      </div>
    );

  return <PacketView packet={analysis.data} />;
}

/** Split from the loader so the job lookup below runs under a stable hook order. */
function PacketView({ packet }: { packet: Analysis }) {
  const job = useJob(packet.job_id ?? undefined);
  const active = useActiveSection(SECTIONS.map((section) => section.id));

  const rejected = packet.suggestions_rejected ?? [];
  const total = packet.suggestions.length + rejected.length;
  // The extraction can return no title (say, a post that never names the role);
  // the job row it came from usually still knows what the reader called it.
  const title = packet.job.title ?? job.data?.title ?? "Untitled job";
  const company = packet.job.company ?? job.data?.company ?? null;

  return (
    <div className="max-w-content space-y-4">
      <header className="space-y-1">
        <nav aria-label="Breadcrumb" className="text-caption text-muted">
          <Link to="/jobs" className="underline">
            Jobs
          </Link>
          {packet.job_id ? (
            <>
              {" / "}
              <Link to={`/jobs/${packet.job_id}`} className="underline">
                {title}
              </Link>
            </>
          ) : null}
          {" / packet"}
        </nav>
        <h1 className="text-title">{title}</h1>
        {company ? <p className="text-dense text-muted">{company}</p> : null}
        <Provenance
          model={packet.model}
          bundle={packet.prompt_bundle}
          runs={packet.match_runs}
          createdAt={packet.created_at}
        />
      </header>

      <SectionNav active={active} />

      <div id="summary" className="scroll-mt-20">
        <PacketSummary summary={packet.summary} />
      </div>

      <div id="matches" className="scroll-mt-20">
        <PacketMatches
          matches={packet.matches}
          requirements={packet.requirements}
        />
      </div>

      <div id="suggestions" className="scroll-mt-20">
        <PacketSuggestions
          analysisId={packet.id}
          suggestions={packet.suggestions}
          rejected={rejected}
          total={total}
          hidden={rejected.length}
        />
      </div>

      <div id="cover" className="scroll-mt-20">
        {packet.cover_note ? (
          <PacketCoverNote analysisId={packet.id} note={packet.cover_note} />
        ) : (
          <section aria-labelledby="cover-heading" className="space-y-2">
            <h2 id="cover-heading" className="text-section">
              Cover note
            </h2>
            <p className="text-dense text-muted">
              No draft was stored for this packet.
            </p>
          </section>
        )}
      </div>

      <div id="jobtext" className="scroll-mt-20">
        <section aria-labelledby="jobtext-heading" className="space-y-2">
          <h2 id="jobtext-heading" className="text-section">
            Job as read
          </h2>
          <SnapshotText snapshotId={packet.snapshot_id} />
        </section>
      </div>

      {packet.job_id ? (
        <JobHistory jobId={packet.job_id} cvVersionId={packet.cv_version_id} />
      ) : null}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
        <a
          href={`/api/analyses/${packet.id}/export.md`}
          download={`analysis-${packet.id.slice(0, 8)}.md`}
          className="text-dense text-accent underline"
        >
          Export as Markdown
        </a>
        <span className="text-caption text-muted">
          The export is plain text; nothing here is rendered as HTML.
        </span>
      </div>
    </div>
  );
}
