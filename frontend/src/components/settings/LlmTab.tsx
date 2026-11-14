import type { Settings } from "@/api/settings";
import { NumberField, TextField } from "@/components/settings/Fields";

const RUN_CHOICES = [1, 2, 3, 4, 5];

export function LlmTab({
  settings,
  apiKey,
  onApiKeyChange,
  onChange,
}: {
  settings: Settings;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  onChange: (next: Settings) => void;
}) {
  const { llm, budget } = settings;

  return (
    <div className="space-y-8">
      <section aria-labelledby="model" className="space-y-3">
        <div>
          <h2 id="model" className="text-section">
            Model
          </h2>
          <p className="mt-1 text-dense text-muted">
            Any OpenAI-compatible endpoint. The host in the base URL is the host
            that receives redacted CV and job text and nothing else.
          </p>
        </div>
        <TextField
          label="Base URL"
          type="url"
          value={llm.base_url}
          onChange={(base_url) =>
            onChange({ ...settings, llm: { ...llm, base_url } })
          }
          placeholder="https://api.deepseek.com/v1"
        />
        <TextField
          label="Model"
          value={llm.model}
          onChange={(model) =>
            onChange({ ...settings, llm: { ...llm, model } })
          }
          placeholder="deepseek-chat"
        />
        <TextField
          label="API key"
          type="password"
          value={apiKey}
          onChange={onApiKeyChange}
          placeholder={
            llm.api_key_set
              ? "A key is stored; leave empty to keep it"
              : "No key stored"
          }
          hint="Stored in the OS keychain, never in the database and never in a log."
        />
      </section>

      <section aria-labelledby="judgment" className="space-y-3">
        <h2 id="judgment" className="text-section">
          Judgment
        </h2>
        <div>
          <label htmlFor="runs" className="block text-dense font-medium">
            Runs per requirement
          </label>
          <select
            id="runs"
            value={llm.runs}
            onChange={(event) =>
              onChange({
                ...settings,
                llm: { ...llm, runs: Number(event.target.value) },
              })
            }
            className="mt-1 rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
          >
            {RUN_CHOICES.map((count) => (
              <option key={count} value={count}>
                {count}
              </option>
            ))}
          </select>
          <p className="mt-1 text-caption text-muted">
            Verdicts are decided by majority. One run is cheaper and volatile;
            three is the default for a reason.
          </p>
        </div>
        <div>
          <label htmlFor="temperature" className="block text-dense font-medium">
            Temperature
          </label>
          <div className="mt-1 flex items-center gap-3">
            <input
              id="temperature"
              type="range"
              min={0}
              max={0.2}
              step={0.05}
              value={llm.temperature}
              onChange={(event) =>
                onChange({
                  ...settings,
                  llm: { ...llm, temperature: Number(event.target.value) },
                })
              }
              className="w-48"
            />
            <span className="text-dense tabular-nums">
              {llm.temperature.toFixed(2)}
            </span>
          </div>
          <p className="mt-1 text-caption text-muted">
            Capped at 0.2. Higher values make the verdicts drift; they do not
            make them better.
          </p>
        </div>
      </section>

      <section aria-labelledby="budget" className="space-y-3">
        <div>
          <h2 id="budget" className="text-section">
            Budget
          </h2>
          <p className="mt-1 text-dense text-muted">
            A soft ceiling on the token count recorded for a month. Empty means
            no ceiling.
          </p>
        </div>
        <NumberField
          label="Monthly tokens"
          value={budget.monthly_tokens}
          min={0}
          step={100000}
          placeholder="2000000"
          onChange={(monthly_tokens) =>
            onChange({ ...settings, budget: { monthly_tokens } })
          }
        />
      </section>
    </div>
  );
}
