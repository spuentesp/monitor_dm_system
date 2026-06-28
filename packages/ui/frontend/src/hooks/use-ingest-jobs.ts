"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ingestApi } from "@/lib/api";
import { FORGE_KEYS } from "@/lib/query-keys";
import type { IngestJob } from "@/lib/types";
import { mergeJobsSafely } from "@/components/forge/ingest/ingest-constants";

/**
 * Polling query for the live ingest job list. Shared by the dashboard,
 * jobs list, and source library. Reuses the previous cached list when
 * `mergeJobsSafely` produces a stable result so transient empty
 * responses during a poll don't visually clear the table.
 */
export function useIngestJobs() {
  const qc = useQueryClient();
  const { data: jobs = [], isLoading } = useQuery<IngestJob[]>({
    queryKey: FORGE_KEYS.jobs,
    queryFn: async () => {
      const incoming = await ingestApi.listJobs();
      const prev = qc.getQueryData<IngestJob[]>(FORGE_KEYS.jobs);
      return mergeJobsSafely(prev, incoming);
    },
    staleTime: 5_000,
    refetchInterval: 5_000,
  });
  return { jobs, isLoading };
}