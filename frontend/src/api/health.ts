import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

/** Reported as free-form JSON by the backend, so the shape is stated here. */
export type Health = {
  status: string;
  database: string;
  gmail: string;
  llm: string;
  checked_at: string;
};

/** Shared so a settings save can tell health that its answer changed. */
export const HEALTH_KEY = ["health"];

export function useHealth() {
  return useQuery({
    queryKey: HEALTH_KEY,
    queryFn: async ({ signal }): Promise<Health> => {
      const report = await api.get("/api/health", { signal });
      return report as unknown as Health;
    },
    refetchInterval: 30_000,
  });
}

const PHRASES: Record<string, string> = {
  ok: "Connected",
  connected: "Connected",
  error: "Error",
  degraded: "Degraded",
  not_connected: "Not connected",
  not_configured: "Not configured",
  auth_failed: "Key rejected",
  keyring_locked: "Keyring locked",
  unreachable: "Unreachable",
  unknown: "Unknown",
};

/** Every status string maps to words; colour alone never carries the meaning. */
export function describeStatus(value: string): string {
  return PHRASES[value] ?? value;
}
