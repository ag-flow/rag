import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frIntegration from "@/i18n/fr/integration.json";
import { IntegrationContractsPage } from "@/pages/IntegrationContractsPage";

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["integration"],
    defaultNS: "integration",
    resources: { fr: { integration: frIntegration } },
    interpolation: { escapeValue: false },
  });
});

function renderPage() {
  return render(
    <I18nextProvider i18n={testI18n}>
      <IntegrationContractsPage />
    </I18nextProvider>,
  );
}

describe("IntegrationContractsPage", () => {
  it("expose l'URL du contrat d'events workflow à importer", () => {
    renderPage();
    const url = `${window.location.origin}/api/contracts/workflow-events`;
    expect(screen.getByText(url)).toBeInTheDocument();
    // Un lien « Voir » pointe dessus.
    const link = screen.getAllByRole("link").find((a) => a.getAttribute("href") === url);
    expect(link).toBeDefined();
  });

  it("liste aussi les contrats REST et MCP", () => {
    renderPage();
    expect(
      screen.getByText(`${window.location.origin}/openapi.json`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${window.location.origin}/api/contracts/mcp-tools`),
    ).toBeInTheDocument();
  });
});
