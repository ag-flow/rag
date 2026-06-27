import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspacesApi } from "@/lib/workspaces";
import type { IndexKeyStrategy } from "@/lib/workspaces.types";

export function useIndexKeys(workspaceName: string, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", workspaceName, "index-keys"],
    queryFn: () => workspacesApi.listIndexKeys(workspaceName),
    enabled,
  });
}

export function useIndexKeyDetail(
  workspaceName: string,
  path: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["workspace", workspaceName, "index-keys", path],
    queryFn: () => workspacesApi.getIndexKeyDetail(workspaceName, path),
    enabled,
  });
}

export function usePatchStrategy(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, strategy }: { path: string; strategy: IndexKeyStrategy }) =>
      workspacesApi.patchIndexKeyStrategy(workspaceName, path, { strategy }),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["workspace", workspaceName, "index-keys"],
      });
    },
  });
}
