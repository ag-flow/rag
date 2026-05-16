import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import frCommon from "@/i18n/fr/common.json";
import frAuth from "@/i18n/fr/auth.json";
import frNav from "@/i18n/fr/nav.json";
import frWorkspaces from "@/i18n/fr/workspaces.json";

import enCommon from "@/i18n/en/common.json";
import enAuth from "@/i18n/en/auth.json";
import enNav from "@/i18n/en/nav.json";
import enWorkspaces from "@/i18n/en/workspaces.json";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "fr",
    supportedLngs: ["fr", "en"],
    ns: ["common", "auth", "nav", "workspaces"],
    defaultNS: "common",
    resources: {
      fr: {
        common: frCommon,
        auth: frAuth,
        nav: frNav,
        workspaces: frWorkspaces,
      },
      en: {
        common: enCommon,
        auth: enAuth,
        nav: enNav,
        workspaces: enWorkspaces,
      },
    },
    interpolation: { escapeValue: false },
  });

export default i18n;
