import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileCode2, Github } from "lucide-react";

import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useAuthMethods } from "@/hooks/useAuthMethods";
import { useVersionInfo } from "@/hooks/usePublicInfo";
import { HeroPanel } from "@/pages/login/HeroPanel";
import { LoginCard } from "@/pages/login/LoginCard";
import { SetupCard } from "@/pages/login/SetupCard";

const GITHUB_URL = "https://github.com/ag-flow/rag";

function getNextFromSearch(): string {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("\\")) {
    return next;
  }
  return "/workspaces";
}

/** Liens publics du panneau droit : dépôt GitHub + contrats d'API. */
function TopLinks() {
  const { t } = useTranslation("login");
  return (
    <div className="flex items-center justify-end gap-4 p-4">
      <a
        href={GITHUB_URL}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
      >
        <Github className="h-4 w-4" aria-hidden="true" />
        {t("github_link")}
      </a>
      <a
        href="/docs"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
      >
        <FileCode2 className="h-4 w-4" aria-hidden="true" />
        {t("contracts_link")}
      </a>
    </div>
  );
}

/** Pied de page : version d'API, environnement, bascule de langue. */
function Footer() {
  const { i18n } = useTranslation("login");
  const { data: info } = useVersionInfo();

  const langButton = (lng: "fr" | "en") => (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(lng)}
      className={
        i18n.resolvedLanguage === lng
          ? "font-semibold text-slate-700"
          : "text-slate-400 hover:text-slate-600"
      }
    >
      {lng}
    </button>
  );

  return (
    <footer className="flex items-center justify-center gap-2 p-4 font-mono text-xs text-slate-400">
      {info && (
        <>
          <span>api {info.version}</span>
          <span aria-hidden="true">·</span>
          <span>{info.environment}</span>
          <span aria-hidden="true">·</span>
        </>
      )}
      {langButton("fr")}
      <span aria-hidden="true">/</span>
      {langButton("en")}
    </footer>
  );
}

/** Écran de connexion scindé (feature 2ca3ceb8) : présentation produit à
 * gauche (masquée < 900 px), authentification à droite — connexion locale en
 * premier, OIDC en secondaire, variante setup au premier démarrage. */
export function LoginPage() {
  const { data: methods, isLoading } = useAuthMethods();
  // Premier démarrage : la variante setup est proposée d'office (et reste la
  // seule atteignable via le lien bas de carte — critère de la fiche).
  const [mode, setMode] = useState<"login" | "setup" | null>(null);

  if (isLoading || !methods) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <LoadingSpinner />
      </div>
    );
  }

  const nextPath = getNextFromSearch();
  const effectiveMode = mode ?? (methods.needs_setup ? "setup" : "login");
  const showSetup = effectiveMode === "setup" && methods.needs_setup;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <HeroPanel />
      <main className="flex min-w-0 flex-1 flex-col">
        <TopLinks />
        <div className="flex flex-1 items-center justify-center p-6">
          {showSetup ? (
            <SetupCard nextPath={nextPath} onBack={() => setMode("login")} />
          ) : (
            <LoginCard methods={methods} nextPath={nextPath} onSetup={() => setMode("setup")} />
          )}
        </div>
        <Footer />
      </main>
    </div>
  );
}
