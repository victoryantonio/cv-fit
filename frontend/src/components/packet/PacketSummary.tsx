import type { Summary } from "@/api/analysis";
import {
  constraintKindLabel,
  constraintStatusLabel,
  fitLabel,
  verdictLabel,
} from "@/lib/packet";

type Flag = Summary["constraint_flags"][number];

const STATUS_STYLES: Record<string, string> = {
  ok: "border-strong-line bg-strong-bg text-strong-fg",
  conflict: "border-gap-line bg-gap-bg text-gap-fg",
  review: "border-partial-line bg-partial-bg text-partial-fg",
  not_stated: "border-line bg-panel text-muted",
};

/**
 * The user's non-negotiables against what the post states. Informational only:
 * a conflict is reported here and never changes a verdict or hides a row.
 * Quiet flags collapse to a count, because five "not stated" lines bury the
 * one flag that actually needs a look.
 */
function Constraints({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) return null;
  const attention = flags.filter(
    (flag) => flag.status === "conflict" || flag.status === "review",
  );
  const quiet = flags.length - attention.length;
  return (
    <div id="constraints" className="space-y-1">
      {attention.length > 0 ? (
        <ul aria-label="Constraints" className="space-y-1">
          {attention.map((flag) => (
            <li
              key={`${flag.kind}-${flag.status}`}
              className={`rounded-md border px-3 py-2 text-dense ${STATUS_STYLES[flag.status] ?? "border-line bg-panel"}`}
            >
              <span className="font-medium">
                {constraintKindLabel(flag.kind)}
              </span>
              : {flag.note}{" "}
              <span className="text-caption opacity-80">
                {constraintStatusLabel(flag.status)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {quiet > 0 ? (
        <p className="text-caption text-muted">
          {quiet === 1
            ? "1 other constraint matches or is not stated in the post."
            : `${quiet} other constraints match or are not stated in the post.`}
        </p>
      ) : null}
    </div>
  );
}

function ItemList({
  title,
  items,
}: {
  title: string;
  items: Summary["strongest"];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-dense font-medium">{title}</h3>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        {items.map((item) => (
          <li key={item.requirement_id} className="text-dense">
            {item.text}
            {item.verdict ? ` · ${verdictLabel(item.verdict)}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Every number and label here is assembled by the server from verified
 * matches. No model wrote this prose, so there is nothing to re-word.
 */
export function PacketSummary({ summary }: { summary: Summary }) {
  return (
    <section aria-labelledby="summary-heading" className="space-y-3">
      <h2 id="summary-heading" className="text-section">
        Summary
      </h2>
      <Constraints flags={summary.constraint_flags} />

      <div className="space-y-3 rounded-lg border border-line bg-panel p-4">
        <p className="text-section">{fitLabel(summary.label)}</p>
        <p className="tabular text-dense">
          Strong {summary.counts.strong ?? 0} · Partial{" "}
          {summary.counts.partial ?? 0} · Gap {summary.counts.gap ?? 0}
        </p>
        <p className="text-dense">
          Must-haves: {summary.must_have.met} of {summary.must_have.total}{" "}
          covered · Coverage {summary.coverage}%
        </p>
        {summary.knockout_gaps.length > 0 ? (
          <p className="text-dense text-gap-fg">
            {summary.knockout_gaps.length === 1
              ? "1 knockout gap: "
              : `${summary.knockout_gaps.length} knockout gaps: `}
            {summary.knockout_gaps.map((item) => item.text).join(" · ")}
          </p>
        ) : null}
        {summary.unstable_count > 0 ? (
          <p className="text-dense text-muted">
            {summary.unstable_count === 1
              ? "1 requirement had runs that disagreed; the weaker verdict was kept."
              : `${summary.unstable_count} requirements had runs that disagreed; the weaker verdict was kept.`}
          </p>
        ) : null}
        <ItemList title="Strongest matches" items={summary.strongest} />
        <ItemList title="Biggest gaps" items={summary.biggest_gaps} />
      </div>
    </section>
  );
}
