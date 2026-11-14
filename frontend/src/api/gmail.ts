/**
 * Gmail consent lives in the helper process (D1), so this app can only report
 * state, hand over the command to run, and forget the stored token.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { isApiError } from "./client";

export type GmailStatus = { status: string; command: string | null };

export function useConnectGmail() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<GmailStatus> => {
      const reply = await api.post("/api/gmail/connect");
      return reply as unknown as GmailStatus;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["health"] });
    },
  });
}

/** The command the server wants run, when it refuses because nothing is connected. */
export function commandFromError(error: unknown): string | null {
  if (!isApiError(error)) return null;
  const command = error.details.command;
  return typeof command === "string" ? command : null;
}

export function useDisconnectGmail() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<GmailStatus> => {
      const reply = await api.post("/api/gmail/disconnect");
      return reply as unknown as GmailStatus;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["health"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
