import type {
  Criteria,
  NonNegotiables,
  Settings,
  WorkMode,
} from "@/api/settings";
import {
  ListField,
  NumberField,
  TextField,
} from "@/components/settings/Fields";

const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Onsite" },
];

export function CriteriaTab({
  settings,
  onChange,
}: {
  settings: Settings;
  onChange: (next: Settings) => void;
}) {
  const { criteria, non_negotiables: rules } = settings;

  function setCriteria(patch: Partial<Criteria>) {
    onChange({ ...settings, criteria: { ...criteria, ...patch } });
  }

  function setRules(patch: Partial<NonNegotiables>) {
    onChange({ ...settings, non_negotiables: { ...rules, ...patch } });
  }

  function toggleMode(mode: WorkMode) {
    const modes = rules.work_modes.includes(mode)
      ? rules.work_modes.filter((item) => item !== mode)
      : [...rules.work_modes, mode];
    setRules({ work_modes: modes });
  }

  const floor = rules.salary_floor;

  return (
    <div className="space-y-8">
      <section aria-labelledby="prefilter" className="space-y-3">
        <div>
          <h2 id="prefilter" className="text-section">
            Pre-filter
          </h2>
          <p className="mt-1 text-dense text-muted">
            Used to flag incoming alerts before you read them. Nothing is hidden
            or dropped.
          </p>
        </div>
        <ListField
          label="Include keywords"
          values={criteria.include_keywords}
          onChange={(include_keywords) => setCriteria({ include_keywords })}
          hint="Separate entries with commas."
          placeholder="python, backend, platform"
        />
        <ListField
          label="Exclude keywords"
          values={criteria.exclude_keywords}
          onChange={(exclude_keywords) => setCriteria({ exclude_keywords })}
          placeholder="unpaid, commission only"
        />
        <ListField
          label="Locations"
          values={criteria.locations}
          onChange={(locations) => setCriteria({ locations })}
          placeholder="Remote, Jakarta, Singapore"
        />
        <ListField
          label="Seniority"
          values={criteria.seniority}
          onChange={(seniority) => setCriteria({ seniority })}
          placeholder="senior, staff"
        />
      </section>

      <section aria-labelledby="non-negotiables" className="space-y-3">
        <div>
          <h2 id="non-negotiables" className="text-section">
            Non-negotiables
          </h2>
          <p className="mt-1 text-dense text-muted">
            A local mirror of your own limits. It is compared with what a post
            states; it is not synced with any job site.
          </p>
        </div>
        <ListField
          label="Languages"
          values={rules.languages}
          onChange={(languages) => setRules({ languages })}
          placeholder="english, indonesian"
        />
        <ListField
          label="Acceptable locations"
          values={rules.locations}
          onChange={(locations) => setRules({ locations })}
          placeholder="Remote, Singapore"
        />
        <fieldset>
          <legend className="text-dense font-medium">Work modes</legend>
          <div className="mt-1 flex flex-wrap gap-4">
            {WORK_MODES.map((mode) => (
              <label
                key={mode.value}
                className="flex items-center gap-2 text-dense"
              >
                <input
                  type="checkbox"
                  checked={rules.work_modes.includes(mode.value)}
                  onChange={() => toggleMode(mode.value)}
                  className="size-4 rounded-sm border-line"
                />
                {mode.label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          <NumberField
            label="Salary floor"
            value={floor?.amount ?? null}
            min={0}
            step={100}
            hint="Leave empty if you have no floor."
            onChange={(amount) =>
              setRules({
                salary_floor:
                  amount === null
                    ? null
                    : { amount, currency: floor?.currency ?? "" },
              })
            }
          />
          <TextField
            label="Currency"
            value={floor?.currency ?? ""}
            maxLength={3}
            placeholder="IDR"
            onChange={(currency) =>
              setRules({
                salary_floor:
                  floor === null || floor === undefined
                    ? null
                    : {
                        amount: floor.amount,
                        currency: currency.toUpperCase(),
                      },
              })
            }
          />
        </div>
        <TextField
          label="Work authorization"
          value={rules.work_authorization ?? ""}
          placeholder="Indonesian citizen; no sponsorship needed"
          onChange={(value) =>
            setRules({ work_authorization: value.trim() || null })
          }
          hint="Free text. It is quoted back to you when a post mentions sponsorship."
        />
      </section>
    </div>
  );
}
