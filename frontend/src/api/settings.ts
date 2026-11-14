/**
 * Settings data access. The read shape is declared here because the backend
 * returns free-form JSON; the write body reuses the generated schema type, so a
 * backend field rename breaks this file instead of silently dropping a value.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { HEALTH_KEY } from "./health";
import type { components } from "./schema";

export type Criteria = {
  include_keywords: string[];
  exclude_keywords: string[];
  locations: string[];
  seniority: string[];
};

export type WorkMode = "remote" | "hybrid" | "onsite";

export type NonNegotiables = {
  languages: string[];
  locations: string[];
  work_modes: WorkMode[];
  salary_floor: { amount: number; currency: string } | null;
  work_authorization: string | null;
};

export type LlmSettings = {
  base_url: string;
  model: string;
  runs: number;
  temperature: number;
  /** Never the key itself: the backend only reports whether one is stored. */
  api_key_set: boolean;
};

export type Settings = {
  criteria: Criteria;
  non_negotiables: NonNegotiables;
  llm: LlmSettings;
  budget: { monthly_tokens: number | null };
  redaction: { terms: string[] };
};

const SETTINGS_KEY = ["settings"] as const;

export function useSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: async ({ signal }): Promise<Settings> => {
      const payload = await api.get("/api/settings", { signal });
      return payload as unknown as Settings;
    },
  });
}

export type SaveVariables = { settings: Settings; apiKey?: string };

/**
 * One PUT carries the whole document: the backend replaces what it stored, so a
 * partial body would blank every section the form did not touch. An empty key
 * field means "keep the stored key", never "erase it".
 */
function toPayload({
  settings,
  apiKey,
}: SaveVariables): components["schemas"]["AppSettings"] {
  const llm: components["schemas"]["LlmSettings"] = {
    base_url: settings.llm.base_url,
    model: settings.llm.model,
    runs: settings.llm.runs,
    temperature: settings.llm.temperature,
    ...(apiKey ? { api_key: apiKey } : {}),
  };
  return {
    criteria: settings.criteria,
    non_negotiables: settings.non_negotiables,
    llm,
    budget: settings.budget,
    redaction: settings.redaction,
  };
}

export function useSaveSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (variables: SaveVariables) =>
      api.put("/api/settings", { body: toPayload(variables) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
      // Storing a key changes what health reports; without this the header keeps
      // saying "Not configured" until the 30 s poll or a reload.
      void queryClient.invalidateQueries({ queryKey: HEALTH_KEY });
    },
  });
}

/** Trims, drops blanks and keeps the order the user typed. */
export function cleanList(values: string[]): string[] {
  return values
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}
