import * as Tabs from "@radix-ui/react-tabs";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import {
  cleanList,
  useSaveSettings,
  useSettings,
  type Settings as SettingsDoc,
} from "@/api/settings";
import { Button } from "@/components/Button";
import { CriteriaTab } from "@/components/settings/CriteriaTab";
import { GmailTab } from "@/components/settings/GmailTab";
import { LlmTab } from "@/components/settings/LlmTab";
import { PrivacyTab } from "@/components/settings/PrivacyTab";
import { clsx } from "clsx";

const TABS = [
  { value: "criteria", label: "Criteria" },
  { value: "llm", label: "Model" },
  { value: "privacy", label: "Privacy and data" },
  { value: "gmail", label: "Gmail" },
] as const;

/** Trims the lists the user typed, so the stored document has no blank entries. */
function tidy(settings: SettingsDoc): SettingsDoc {
  return {
    criteria: {
      include_keywords: cleanList(settings.criteria.include_keywords),
      exclude_keywords: cleanList(settings.criteria.exclude_keywords),
      locations: cleanList(settings.criteria.locations),
      seniority: cleanList(settings.criteria.seniority),
    },
    non_negotiables: {
      languages: cleanList(settings.non_negotiables.languages),
      locations: cleanList(settings.non_negotiables.locations),
      work_modes: settings.non_negotiables.work_modes,
      salary_floor: settings.non_negotiables.salary_floor,
      work_authorization:
        settings.non_negotiables.work_authorization?.trim() ?? null,
    },
    llm: settings.llm,
    budget: settings.budget,
    redaction: { terms: cleanList(settings.redaction.terms) },
  };
}

/**
 * Repeats the rules the API enforces, so the user sees the problem next to the
 * field instead of as a 422 after pressing Save.
 */
function invalidReason(settings: SettingsDoc): string | null {
  const { llm, non_negotiables: rules, redaction } = settings;
  const floor = rules.salary_floor;
  if (floor && floor.currency.trim().length !== 3) {
    return "A salary floor needs a three-letter currency, for example IDR.";
  }
  const https = llm.base_url.trim().toLowerCase().startsWith("https://");
  const local =
    llm.base_url.trim().startsWith("http://127.0.0.1") ||
    llm.base_url.trim().startsWith("http://localhost") ||
    llm.base_url.trim().startsWith("http://[::1]");
  if (!https && !local) {
    return "The base URL must use HTTPS, or plain HTTP on localhost.";
  }
  if (cleanList(redaction.terms).some((term) => term.length < 2)) {
    return "A redaction term needs at least two characters.";
  }
  return null;
}

function sameDocument(left: SettingsDoc, right: SettingsDoc): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function Settings() {
  const settings = useSettings();
  const save = useSaveSettings();
  const [draft, setDraft] = useState<SettingsDoc | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [tab, setTab] = useState<string>("criteria");

  if (settings.isPending) {
    return <p className="text-dense text-muted">Loading settings...</p>;
  }
  if (settings.isError) {
    return (
      <p className="text-dense text-danger">{errorMessage(settings.error)}</p>
    );
  }

  const stored = tidy(settings.data);
  const current = draft ?? stored;
  const document = tidy(current);
  const dirty = !sameDocument(document, stored) || apiKey.trim() !== "";
  const problem = invalidReason(document);

  function apply(next: SettingsDoc) {
    setDraft(next);
  }

  function onSave() {
    save.mutate(
      { settings: document, apiKey: apiKey.trim() || undefined },
      {
        onSuccess: () => {
          setDraft(null);
          setApiKey("");
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-content px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-title">Settings</h1>
          <p className="mt-1 text-dense text-muted">
            Applies to this machine only. Nothing here is shared or synced.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty ? (
            <span className="text-caption text-muted">Unsaved changes</span>
          ) : null}
          <Button
            variant="primary"
            busy={save.isPending}
            disabled={!dirty || problem !== null}
            onClick={onSave}
          >
            Save
          </Button>
        </div>
      </header>

      {problem && tab !== "gmail" ? (
        <p role="alert" className="mt-3 text-dense text-danger">
          {problem}
        </p>
      ) : null}
      {save.isError ? (
        <p role="alert" className="mt-3 text-dense text-danger">
          {errorMessage(save.error)}
        </p>
      ) : null}
      {save.isSuccess && !dirty ? (
        <p role="status" className="mt-3 text-dense text-muted">
          Saved.
        </p>
      ) : null}

      <Tabs.Root value={tab} onValueChange={setTab} className="mt-6">
        <Tabs.List
          aria-label="Settings sections"
          className="flex flex-wrap gap-1 border-b border-line"
        >
          {TABS.map((item) => (
            <Tabs.Trigger
              key={item.value}
              value={item.value}
              className={clsx(
                "border-b-2 border-transparent px-3 py-2 text-dense text-muted",
                "data-[state=active]:border-accent data-[state=active]:text-ink",
              )}
            >
              {item.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="criteria" className="pt-6">
          <CriteriaTab settings={current} onChange={apply} />
        </Tabs.Content>
        <Tabs.Content value="llm" className="pt-6">
          <LlmTab
            settings={current}
            apiKey={apiKey}
            onApiKeyChange={setApiKey}
            onChange={apply}
          />
        </Tabs.Content>
        <Tabs.Content value="privacy" className="pt-6">
          <PrivacyTab settings={current} onChange={apply} />
        </Tabs.Content>
        <Tabs.Content value="gmail" className="pt-6">
          <GmailTab />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
