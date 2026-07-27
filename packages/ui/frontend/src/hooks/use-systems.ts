import { useQuery } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import { ENTITY_KEYS } from "@/lib/query-keys";
import type { RPGSystem } from "@/lib/types";

export function useSystems() {
  return useQuery<RPGSystem[]>({
    queryKey: ENTITY_KEYS.systems,
    queryFn: entitiesApi.listSystems,
    staleTime: 30_000,
  });
}

export function useSystem(id?: string | null) {
  return useQuery<RPGSystem | null>({
    queryKey: id ? ENTITY_KEYS.system(id) : ["system", null],
    queryFn: () => (id ? entitiesApi.getSystem(id) : Promise.resolve(null)),
    enabled: !!id,
    staleTime: 30_000,
  });
}
