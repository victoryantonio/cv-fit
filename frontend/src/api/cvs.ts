/**
 * CV data access. Types come from the generated schema, so a backend field
 * rename breaks the build instead of surfacing as an undefined at runtime.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type CvListItem = components["schemas"]["CvListItem"];
export type CvCreate = components["schemas"]["CvCreate"];
export type CvOut = components["schemas"]["CvOut"];
export type VersionOut = components["schemas"]["VersionOut"];
export type ParserViewOut = components["schemas"]["ParserViewOut"];

const CVS_KEY = ["cvs"] as const;

export function useCvs() {
  return useQuery({
    queryKey: CVS_KEY,
    queryFn: async ({ signal }) => {
      const page = await api.get("/api/cvs", { signal });
      return page.items;
    },
  });
}

/** The stored redacted text: exactly what a model would receive. */
export function useParserView(versionId: string | undefined) {
  return useQuery({
    queryKey: ["cv-version", versionId, "parser-view"],
    enabled: Boolean(versionId),
    queryFn: async ({ signal }): Promise<ParserViewOut> => {
      if (!versionId) throw new Error("A version id is required.");
      return api.get("/api/cv-versions/{version_id}/parser-view", {
        params: { version_id: versionId },
        signal,
      });
    },
  });
}

export function useCreateCv(): UseMutationResult<CvOut, Error, CvCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CvCreate): Promise<CvOut> =>
      api.post<"/api/cvs", 201>("/api/cvs", { body: payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CVS_KEY });
    },
  });
}

export type UploadVariables = { cvId: string; file: File; note?: string };

/**
 * One multipart request: the file plus an optional note. The server rejects a
 * duplicate file with CONFLICT and points at the existing version.
 */
export function useUploadVersion(): UseMutationResult<
  VersionOut,
  Error,
  UploadVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      cvId,
      file,
      note,
    }: UploadVariables): Promise<VersionOut> => {
      const form = new FormData();
      form.append("file", file);
      if (note?.trim()) form.append("note", note.trim());
      return api.postForm("/api/cvs/{cv_id}/versions", form, {
        params: { cv_id: cvId },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CVS_KEY });
    },
  });
}
