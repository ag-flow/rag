import { createContext, useContext, type ReactNode } from "react";
import { useMe } from "@/hooks/useMe";
import { isUnauthorized } from "@/lib/api";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { MeResponse } from "@/lib/validators";

const UserContext = createContext<MeResponse | null>(null);

export function useUser(): MeResponse {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be inside AuthGuard");
  return ctx;
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const { data, error, isLoading } = useMe();

  if (isLoading) return <LoadingSpinner />;

  if (error && isUnauthorized(error)) {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/auth/login?next=${encodeURIComponent(next)}`;
    return null;
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-destructive">Authentication failed. Please refresh.</div>
    );
  }

  return <UserContext.Provider value={data}>{children}</UserContext.Provider>;
}
