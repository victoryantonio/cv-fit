/**
 * Data controls (FR-26). Everything here stays on this machine: a backup is a
 * file copy, and the export is a plain download the browser saves for you.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type DataSummary = components["schemas"]["DataSummary"];
export type BackupResult = components["schemas"]["BackupResult"];
export type PurgeResult = components["schemas"]["PurgeResult"];

const DATA_KEY = ["data-summary"] as const;

export function useDataSummary() {
  return useQuery({
    queryKey: DATA_KEY,
    queryFn: async ({ signal }) => api.get("/api/data", { signal }),
  });
}

export function useBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<BackupResult> => api.post("/api/backup"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DATA_KEY });
    },
  });
}

/** The word the server demands; repeated here so the dialog can label the field. */
export const PURGE_CONFIRMATION = "DELETE";

export function usePurge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (confirm: string): Promise<PurgeResult> =>
      api.post("/api/data/purge", { body: { confirm } }),
    onSuccess: () => {
      // Everything the app has cached may just have been deleted.
      void queryClient.invalidateQueries();
    },
  });
}
