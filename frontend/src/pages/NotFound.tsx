import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <h1 className="text-4xl font-bold text-slate-300 mb-2">404</h1>
      <p className="text-slate-600 mb-6">Page introuvable.</p>
      <Button asChild>
        <Link to="/workspaces">Retour aux workspaces</Link>
      </Button>
    </div>
  );
}
