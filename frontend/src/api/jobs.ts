import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type Job = components["schemas"]["JobOut"];
export type JobListItem = components["schemas"]["JobListItem"];
export type JobDetail = components["schemas"]["JobDetailOut"];
export type JobCreate = components["schemas"]["JobCreate"];
export type JobPatch = components["schemas"]["JobPatch"];
export type Snapshot = components["schemas"]["SnapshotOut"];
export type SnapshotCreated = components["schemas"]["SnapshotCreateOut"];
export type SnapshotDetail = components["schemas"]["SnapshotDetailOut"];
export type SyncStatus = components["schemas"]["SyncStatusOut"];
export type SyncAlerts = components["schemas"]["SyncAlertsOut"];

export const JOBS_KEY = ["jobs"] as const;
export const SYNC_STATUS_KEY = ["jobs", "sync-status"] as const;

/** The order the inbox offers. `dismissed` is a filter, not a place to work. */
export const JOB_STATUSES = [
  "new",
  "shortlisted",
  "analyzed",
  "applied",
  "dismissed",
] as const;

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  shortlisted: "Shortlisted",
  analyzed: "Analyzed",
  applied: "Applied",
  dismissed: "Dismissed",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export type JobFilters = { status?: string; filtered?: boolean };

export function useJobs(filters: JobFilters = {}) {
  return useQuery({
    queryKey: [...JOBS_KEY, "list", filters],
    queryFn: async ({ signal }) => {
      const page = await api.get("/api/jobs", { query: filters, signal });
      return page.items;
    },
  });
}

export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: [...JOBS_KEY, "detail", jobId],
    enabled: Boolean(jobId),
    queryFn: async ({ signal }): Promise<JobDetail> => {
      if (!jobId) throw new Error("A job id is required.");
      return api.get("/api/jobs/{job_id}", {
        params: { job_id: jobId },
        signal,
      });
    },
  });
}

export function useSnapshot(snapshotId: string | undefined) {
  return useQuery({
    queryKey: [...JOBS_KEY, "snapshot", snapshotId],
    enabled: Boolean(snapshotId),
    queryFn: async ({ signal }): Promise<SnapshotDetail> => {
      if (!snapshotId) throw new Error("A snapshot id is required.");
      return api.get("/api/jd-snapshots/{snapshot_id}", {
        params: { snapshot_id: snapshotId },
        signal,
      });
    },
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: SYNC_STATUS_KEY,
    queryFn: async ({ signal }): Promise<SyncStatus> =>
      api.get("/api/jobs/sync-status", { signal }),
  });
}

export function useCreateJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: JobCreate): Promise<Job> =>
      api.post<"/api/jobs", 201>("/api/jobs", { body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: JOBS_KEY });
    },
  });
}

export function usePatchJob(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: JobPatch): Promise<Job> =>
      api.patch("/api/jobs/{job_id}", { params: { job_id: jobId }, body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: JOBS_KEY });
    },
  });
}

export function useCreateSnapshot(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (rawText: string): Promise<SnapshotCreated> =>
      api.post<"/api/jobs/{job_id}/snapshots", 201>(
        "/api/jobs/{job_id}/snapshots",
        {
          params: { job_id: jobId },
          body: { raw_text: rawText, source_kind: "page_paste" },
        },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: JOBS_KEY });
    },
  });
}

/** Reads Gmail alert emails through the helper process. Never fetches a job page. */
export function useSyncAlerts() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<SyncAlerts> =>
      api.post("/api/jobs/sync-alerts", { body: { limit: 25 } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: JOBS_KEY });
    },
  });
}
