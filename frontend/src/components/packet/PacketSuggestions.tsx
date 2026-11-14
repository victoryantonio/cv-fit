import { useState } from "react";

import { useSetSuggestionDecision, type Suggestion } from "@/api/analysis";
import { errorMessage } from "@/api/client";
import { Button } from "@/components/Button";
import {
  decisionLabel,
  guardExplanation,
  scopeLabel,
  suggestionTypeLabel,
  targetSectionLabel,
} from "@/lib/packet";

function SuggestionRow({
  suggestion,
  analysisId,
}: {
  suggestion: Suggestion;
  analysisId: string;
}) {
  const decide = useSetSuggestionDecision(analysisId);
  const rejected = suggestion.guard_status !== "pass";

  return (
    <li className="space-y-2 rounded-md border border-line bg-panel p-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-dense font-medium">
          {suggestionTypeLabel(suggestion.type)}
        </span>
        <span className="text-caption text-muted">
          {scopeLabel(suggestion.scope)} ·{" "}
          {targetSectionLabel(suggestion.target_section)} ·{" "}
          {decisionLabel(suggestion.decision)}
        </span>
      </div>

      {suggestion.original_text ? (
        <div>
          <p className="text-caption text-muted">In your CV now</p>
          <p className="font-mono text-quote text-ink">
            {suggestion.original_text}
          </p>
        </div>
      ) : null}
      {suggestion.proposed_text ? (
        <div>
          <p className="text-caption text-muted">Proposed wording</p>
          <p className="font-mono text-quote text-ink">
            {suggestion.proposed_text}
          </p>
        </div>
      ) : null}
      {suggestion.rationale ? (
        <p className="text-dense text-muted">{suggestion.rationale}</p>
      ) : null}

      {rejected ? (
        <p className="text-caption text-gap-fg">
          Rejected by the fabrication guard.{" "}
          {guardExplanation(suggestion.guard_status)}{" "}
          {suggestion.guard_reason ? `(${suggestion.guard_reason})` : ""}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button
            busy={decide.isPending}
            disabled={suggestion.decision === "accepted"}
            onClick={() =>
              decide.mutate({
                suggestionId: suggestion.id,
                decision: "accepted",
              })
            }
          >
            Accept
          </Button>
          <Button
            variant="ghost"
            busy={decide.isPending}
            disabled={suggestion.decision === "rejected"}
            onClick={() =>
              decide.mutate({
                suggestionId: suggestion.id,
                decision: "rejected",
              })
            }
          >
            Reject
          </Button>
        </div>
      )}

      {decide.isError ? (
        <p role="alert" className="text-caption text-gap-fg">
          {errorMessage(decide.error)}
        </p>
      ) : null}
    </li>
  );
}

/**
 * Suggestions reword or reorder what the CV already says. Rejected ones are
 * hidden by default but never deleted: the toggle is there so a blunt guard is
 * auditable rather than invisible.
 */
export function PacketSuggestions({
  analysisId,
  suggestions,
  rejected,
  total,
  hidden,
}: {
  analysisId: string;
  suggestions: Suggestion[];
  rejected: Suggestion[];
  total: number;
  hidden: number;
}) {
  const [showRejected, setShowRejected] = useState(false);

  return (
    <section aria-labelledby="suggestions-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="suggestions-heading" className="text-section">
          CV suggestions ({total})
        </h2>
        {rejected.length > 0 ? (
          <label className="flex items-center gap-2 text-caption text-muted">
            <input
              type="checkbox"
              checked={showRejected}
              onChange={(event) => setShowRejected(event.target.checked)}
            />
            Show {hidden} rejected by the guard
          </label>
        ) : null}
      </div>

      {suggestions.length === 0 ? (
        <p className="text-dense text-muted">
          No suggestion passed the guard for this job. That is a result, not an
          error: the guard would rather drop a fair suggestion than let one
          invented fact through.
        </p>
      ) : (
        <ul className="space-y-2">
          {suggestions.map((suggestion) => (
            <SuggestionRow
              key={suggestion.id}
              suggestion={suggestion}
              analysisId={analysisId}
            />
          ))}
        </ul>
      )}

      {showRejected ? (
        <ul className="space-y-2">
          {rejected.map((suggestion) => (
            <SuggestionRow
              key={suggestion.id}
              suggestion={suggestion}
              analysisId={analysisId}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
