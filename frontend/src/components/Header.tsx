// frontend/src/components/Header.tsx
import { useUser } from "@/components/AuthGuard";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, ChevronDown } from "lucide-react";

export function Header() {
  const { t } = useTranslation("auth");
  const user = useUser();

  const initials = (user.name ?? user.email ?? "?")
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  function handleLogout() {
    const isLocal = user.sub === "admin" && user.email === null;
    if (isLocal) {
      void fetch("/auth/local/logout", { method: "POST" }).finally(() => {
        window.location.href = "/ui/login";
      });
      return;
    }
    // OIDC : POST /auth/logout (cookie envoyé), backend redirige vers Keycloak logout.
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/auth/logout";
    document.body.appendChild(form);
    form.submit();
  }

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
      <div />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2">
            <span className="h-7 w-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-semibold">
              {initials}
            </span>
            <span className="text-sm text-slate-700">{user.email ?? user.sub}</span>
            <ChevronDown className="h-4 w-4 text-slate-400" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            {t("logout")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
