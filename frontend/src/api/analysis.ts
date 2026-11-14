/**
 * Analysis data access: start a packet, watch the task that builds it, then
 * read what was stored.
 *
 * `POST /api/analyses` answers two ways — 200 with the stored packet when the
 * cache hits, 202 with a task id when it misses. The fetch wrapper returns the
 * body, not the status, so `useStartAnalysis` narrows on the body shape: only
 * the queued body carries a `task`.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type Analysis = components["schemas"]["AnalysisOut"];
export type AnalysisRun = components["schemas"]["AnalysisRunOut"];
export type AnalysisQueued = components["schemas"]["AnalysisQueuedOut"];
export type Task = components["schemas"]["TaskOut"];
export type Match = components["schemas"]["MatchOut"];
export type Requirement = components["schemas"]["RequirementOut"];
export type Suggestion = components["schemas"]["SuggestionOut"];
export type Summary = components["schemas"]["SummaryOut"];
export type CoverNote = components["schemas"]["CoverNoteOut"];
export type History = components["schemas"]["HistoryOut"];
export type Provenance = components["schemas"]["ProvenanceOut"];

/** Progress is polled, not pushed: one request every 1.5 s while a task runs. */
export const TASK_POLL_MS = 1500;

const TERMINAL: readonly string[] = ["ok", "failed", "cancelled"];

export function isTaskDone(status: string | undefined): boolean {
  return status !== undefined && TERMINAL.includes(status);
}

export function analysisKey(analysisId: string) {
  return ["analysis", analysisId] as const;
}

function cachePacket(client: QueryClient, packet: Analysis) {
  client.setQueryData(analysisKey(packet.id), packet);
}

export function useAnalysis(analysisId: string | undefined) {
  return useQuery({
    queryKey: analysisKey(analysisId ?? ""),
    enabled: Boolean(analysisId),
    queryFn: async ({ signal }): Promise<Analysis> => {
      if (!analysisId) throw new Error("An analysis id is required.");
      return api.get("/api/analyses/{analysis_id}", {
        params: { analysis_id: analysisId },
        // Guard-rejected suggestions stay hidden by default in the UI, but the
        // user can ask to see them, so they come down in one request.
        query: { include_rejected: true },
        signal,
      });
    },
  });
}

export function useTask(taskId: string | undefined) {
  // The explicit generic is load-bearing: without it the self-referential
  // refetchInterval callback cannot see `data.status` and it degrades to {}.
  return useQuery<Task>({
    queryKey: ["task", taskId ?? ""],
    enabled: Boolean(taskId),
    refetchInterval: (query) =>
      isTaskDone(query.state.data?.status) ? false : TASK_POLL_MS,
    queryFn: async ({ signal }): Promise<Task> => {
      if (!taskId) throw new Error("A task id is required.");
      return api.get("/api/tasks/{task_id}", {
        params: { task_id: taskId },
        signal,
      });
    },
  });
}

/** Retry and cancel share a shape: both answer with the task's new state. */
export function useRetryTask(
  taskId: string,
): UseMutationResult<Task, Error, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Task> =>
      api.post("/api/tasks/{task_id}/retry", { params: { task_id: taskId } }),
    onSuccess: (task) => queryClient.setQueryData(["task", taskId], task),
  });
}

export function useCancelTask(
  taskId: string,
): UseMutationResult<Task, Error, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Task> =>
      api.post("/api/tasks/{task_id}/cancel", { params: { task_id: taskId } }),
    onSuccess: (task) => queryClient.setQueryData(["task", taskId], task),
  });
}

export function useHistory(jobId: string | undefined) {
  return useQuery({
    queryKey: ["history", jobId ?? ""],
    enabled: Boolean(jobId),
    queryFn: async ({ signal }): Promise<History> => {
      if (!jobId) throw new Error("A job id is required.");
      return api.get("/api/jobs/{job_id}/history", {
        params: { job_id: jobId },
        signal,
      });
    },
  });
}

export type StartVariables = { cvVersionId: string; snapshotId: string };

/** The two outcomes a start request can have, told apart by body shape. */
export type Started =
  | { kind: "packet"; packet: AnalysisRun }
  | { kind: "queued"; taskId: string };

export function useStartAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      cvVersionId,
      snapshotId,
    }: StartVariables): Promise<Started> => {
      const body = (await api.post("/api/analyses", {
        body: {
          cv_version_id: cvVersionId,
          snapshot_id: snapshotId,
          force: false,
          override_budget: false,
        },
      })) as AnalysisRun | AnalysisQueued;
      if ("task" in body) return { kind: "queued", taskId: body.task.id };
      cachePacket(queryClient, body);
      return { kind: "packet", packet: body };
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useSetRequirementActive(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      requirementId,
      active,
    }: {
      requirementId: string;
      active: boolean;
    }) =>
      api.patch("/api/requirements/{requirement_id}", {
        params: { requirement_id: requirementId },
        body: { active },
      }),
    // The server recomputes coverage, so refetch rather than patching locally.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: analysisKey(analysisId) });
    },
  });
}

export function useSetSuggestionDecision(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      suggestionId,
      decision,
    }: {
      suggestionId: string;
      decision: string;
    }) =>
      api.patch("/api/suggestions/{suggestion_id}", {
        params: { suggestion_id: suggestionId },
        body: { decision },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: analysisKey(analysisId) });
    },
  });
}

export function useSaveCoverNote(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (text: string): Promise<Analysis> =>
      api.patch("/api/analyses/{analysis_id}/cover-note", {
        params: { analysis_id: analysisId },
        body: { text },
      }),
    onSuccess: (packet) => cachePacket(queryClient, packet),
  });
}

export function useRegenerateCoverNote(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Analysis> =>
      api.post("/api/analyses/{analysis_id}/cover-note/regenerate", {
        params: { analysis_id: analysisId },
      }),
    onSuccess: (packet) => cachePacket(queryClient, packet),
  });
}
