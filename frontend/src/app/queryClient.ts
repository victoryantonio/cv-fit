import { QueryClient } from "@tanstack/react-query";

/**
 * One client for the app. Tasks poll on a short interval; everything else is
 * read once and invalidated after a write, so nothing refetches needlessly.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 5_000,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: 0 },
    },
  });
}
