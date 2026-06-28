import { useQuery } from "@tanstack/react-query";
import { llmApi } from "@/lib/api";
import { SETTINGS_KEYS } from "@/lib/query-keys";
import type { LLMConnection, NodeAssignment } from "@/lib/types";

export function useLLMProviders() {
  return useQuery<LLMConnection[]>({
    queryKey: SETTINGS_KEYS.providers,
    queryFn: llmApi.listProviders,
    staleTime: 60_000,
  });
}

export function useLLMAssignments() {
  return useQuery<NodeAssignment[]>({
    queryKey: SETTINGS_KEYS.assignments,
    queryFn: llmApi.listAssignments,
    staleTime: 30_000,
  });
}
