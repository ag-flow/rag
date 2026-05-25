import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MeResponse } from "@/lib/validators";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<MeResponse>("/me"),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}
