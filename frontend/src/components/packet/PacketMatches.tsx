import type { Match, Requirement } from "@/api/analysis";
import {
  importanceLabel,
  matchFlagLabel,
  verdictLabel,
  votesText,
} from "@/lib/packet";

type Row = { match: Match; requirement: Requirement | undefined };

const VERDICT_STYLES: Record<string, string> = {
  strong: "text-strong-fg",
  partial: "text-partial-fg",
  gap: "text-gap-fg",
};

/** Knockout gaps first, then other gaps, then partials; each group in JD order. */
function rank(row: Row): number {
  const knockout = row.requirement?.importance === "knockout";
  if (row.match.verdict === "gap") return knockout ? 0 : 1;
  return 2;
}

function MatchRow({ row }: { row: Row }) {
  const { match, requirement } = row;
  return (
    <li className="rounded-md border border-line bg-panel p-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span
          className={`text-dense font-medium ${VERDICT_STYLES[match.verdict] ?? ""}`}
        >
          {verdictLabel(match.verdict)}
        </span>
        <span className="text-dense">
          {requirement?.text ?? match.requirement_id}
        </span>
        <span className="text-caption text-muted">
          {requirement
            ? importanceLabel(requirement.importance)
            : "Requirement"}{" "}
          · {votesText(match.votes)}
        </span>
        {requirement?.active === false ? (
          <span className="text-caption text-muted">
            Excluded from coverage
          </span>
        ) : null}
      </div>

      {match.evidence_quote ? (
        <figure className="mt-2">
          <figcaption className="text-caption text-muted">
            Evidence in your CV
          </figcaption>
          <blockquote className="mt-1 border-l-2 border-line pl-3 font-mono text-quote text-ink">
            {match.evidence_quote}
          </blockquote>
        </figure>
      ) : null}

      {match.flags.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {match.flags.map((flag) => (
            <li key={flag} className="text-caption text-partial-fg">
              {matchFlagLabel(flag)}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function Group({
  id,
  title,
  rows,
  empty,
}: {
  id: string;
  title: string;
  rows: Row[];
  empty: string;
}) {
  return (
    <section aria-labelledby={`${id}-heading`} className="space-y-2">
      <h3 id={`${id}-heading`} className="text-dense font-medium">
        {title} ({rows.length})
      </h3>
      {rows.length === 0 ? (
        <p className="text-dense text-muted">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <MatchRow key={row.match.requirement_id} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * A gap is reported as a gap. The note under the list says what to do about one
 * without ever suggesting a fact that is not in the CV.
 */
export function PacketMatches({
  matches,
  requirements,
}: {
  matches: Match[];
  requirements: Requirement[];
}) {
  const byId = new Map(
    requirements.map((requirement) => [requirement.id, requirement]),
  );
  const rows: Row[] = matches.map((match) => ({
    match,
    requirement: byId.get(match.requirement_id),
  }));
  const matched = rows.filter((row) => row.match.verdict === "strong");
  const unmatched = rows
    .filter((row) => row.match.verdict !== "strong")
    .sort((a, b) => rank(a) - rank(b));

  return (
    <section aria-labelledby="matches-heading" className="space-y-4">
      <h2 id="matches-heading" className="text-section">
        What matches and what does not
      </h2>
      <Group
        id="matched"
        title="What matches"
        rows={matched}
        empty="No requirement was a strong match."
      />
      <Group
        id="unmatched"
        title="What does not match"
        rows={unmatched}
        empty="Every requirement came back strong."
      />
      {unmatched.length > 0 ? (
        <p className="text-dense text-muted">
          A gap means this CV has no evidence for the requirement. If you have
          that experience, add it truthfully; if not, treat it as a real gap.
        </p>
      ) : null}
    </section>
  );
}
