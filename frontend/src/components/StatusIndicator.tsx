import { cn } from "@/lib/utils";

export type SecretStatus = "present" | "empty" | "missing";

interface Props {
  status: SecretStatus;
  className?: string;
}

const dotClass: Record<SecretStatus, string> = {
  present: "bg-emerald-500",
  empty: "bg-amber-500",
  missing: "bg-red-500",
};

export function StatusIndicator({ status, className }: Props) {
  return (
    <span
      role="status"
      aria-label={`secret-${status}`}
      className={cn("inline-block h-2.5 w-2.5 rounded-full", dotClass[status], className)}
    />
  );
}
