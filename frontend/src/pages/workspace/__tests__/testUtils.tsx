import React from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frCommon from "@/i18n/fr/common.json";
import frAuth from "@/i18n/fr/auth.json";
import frNav from "@/i18n/fr/nav.json";
import frWorkspaces from "@/i18n/fr/workspaces.json";
import frWorkspace from "@/i18n/fr/workspace.json";
import frHarpocrate from "@/i18n/fr/harpocrate.json";

import enCommon from "@/i18n/en/common.json";
import enAuth from "@/i18n/en/auth.json";
import enNav from "@/i18n/en/nav.json";
import enWorkspaces from "@/i18n/en/workspaces.json";
import enWorkspace from "@/i18n/en/workspace.json";
import enHarpocrate from "@/i18n/en/harpocrate.json";

// i18n instance isolée pour les tests, forcée en FR
const testI18n = i18next.createInstance();

void testI18n.use(initReactI18next).init({
  lng: "fr",
  fallbackLng: "fr",
  supportedLngs: ["fr", "en"],
  ns: ["common", "auth", "nav", "workspaces", "workspace", "harpocrate"],
  defaultNS: "common",
  resources: {
    fr: {
      common: frCommon,
      auth: frAuth,
      nav: frNav,
      workspaces: frWorkspaces,
      workspace: frWorkspace,
      harpocrate: frHarpocrate,
    },
    en: {
      common: enCommon,
      auth: enAuth,
      nav: enNav,
      workspaces: enWorkspaces,
      workspace: enWorkspace,
      harpocrate: enHarpocrate,
    },
  },
  interpolation: { escapeValue: false },
});

export function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <I18nextProvider i18n={testI18n}>
        <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}
