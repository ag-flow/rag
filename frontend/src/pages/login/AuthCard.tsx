import type { ReactNode } from "react";

/** Carte encadrée du panneau droit : cadre filaire + marques de repère aux
 * angles (design system Industry). */
export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="relative w-full max-w-md border border-slate-300 bg-white p-6">
      <CornerMark className="-left-px -top-px border-l-2 border-t-2" />
      <CornerMark className="-right-px -top-px border-r-2 border-t-2" />
      <CornerMark className="-bottom-px -left-px border-b-2 border-l-2" />
      <CornerMark className="-bottom-px -right-px border-b-2 border-r-2" />
      {children}
    </div>
  );
}

function CornerMark({ className }: { className: string }) {
  return <span aria-hidden="true" className={`absolute h-3 w-3 border-accent-500 ${className}`} />;
}
