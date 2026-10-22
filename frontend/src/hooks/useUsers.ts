import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usersApi, type UserRole } from "@/lib/users";

const KEY = ["admin-users"] as const;

export function useUsers() {
  return useQuery({ queryKey: KEY, queryFn: () => usersApi.list(), staleTime: 30_000 });
}

export function useSetUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      usersApi.setRole(userId, role),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}
