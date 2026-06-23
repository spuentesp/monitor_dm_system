import { useQuery } from "@tanstack/react-query";
import { dbApi } from "@/lib/api";
import { SETTINGS_KEYS } from "@/lib/query-keys";
import type { DatabaseStatus } from "@/lib/types";

export function useDatabases() {
  return useQuery<DatabaseStatus[]>({
    queryKey: SETTINGS_KEYS.databases,
    queryFn: dbApi.allStatus,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
