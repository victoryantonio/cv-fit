import type { Settings } from "@/api/settings";
import { DataControls } from "@/components/settings/DataControls";
import { ListField } from "@/components/settings/Fields";

/** The bare host, so the note names the destination rather than the URL shape. */
function hostOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).host || "the model provider";
  } catch {
    return "the model provider";
  }
}

export function PrivacyTab({
  settings,
  onChange,
}: {
  settings: Settings;
  onChange: (next: Settings) => void;
}) {
  const terms = settings.redaction.terms;

  return (
    <div className="space-y-8">
      <section aria-labelledby="leaves" className="space-y-2">
        <h2 id="leaves" className="text-section">
          What leaves this machine
        </h2>
        {/* DESIGN.md §267: quiet, but never hidden. */}
        <p className="text-dense">
          Redacted CV and job text goes to{" "}
          <strong>{hostOf(settings.llm.base_url)}</strong>. Phone numbers,
          addresses, ID numbers and email addresses are removed first, along
          with any term you add below.
        </p>
        <p className="text-dense text-muted">
          Nothing else is sent: no files, no health data, no keys. The Gmail
          helper reads alerts read-only, and job pages are only ever pasted by
          you.
        </p>
      </section>

      <section aria-labelledby="redaction" className="space-y-3">
        <div>
          <h2 id="redaction" className="text-section">
            Custom redaction terms
          </h2>
          <p className="mt-1 text-dense text-muted">
            Names, employers, or anything else you would rather the model never
            sees. Matching is literal and case-insensitive.
          </p>
        </div>
        <ListField
          label="Terms"
          values={terms}
          onChange={(next) =>
            onChange({ ...settings, redaction: { terms: next } })
          }
          placeholder="your full name, current employer"
          hint="These are additionally masked as [REDACTED]."
        />
      </section>

      <section aria-labelledby="data" className="space-y-3">
        <div>
          <h2 id="data" className="text-section">
            Your data
          </h2>
          <p className="mt-1 text-dense text-muted">
            Everything lives in a SQLite file and an uploads folder on this
            machine.
          </p>
        </div>
        <DataControls />
      </section>
    </div>
  );
}
