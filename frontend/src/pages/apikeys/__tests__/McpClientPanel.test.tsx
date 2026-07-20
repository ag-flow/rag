import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frApikeys from "@/i18n/fr/apikeys.json";
import { McpClientPanel } from "../McpClientPanel";

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["apikeys"],
    defaultNS: "apikeys",
    resources: { fr: { apikeys: frApikeys } },
    interpolation: { escapeValue: false },
  });
  // window.location.origin est http://localhost dans jsdom.
});

function renderPanel(props: Parameters<typeof McpClientPanel>[0]) {
  return render(
    <I18nextProvider i18n={testI18n}>
      <McpClientPanel {...props} />
    </I18nextProvider>,
  );
}

describe("McpClientPanel", () => {
  it("expose un endpoint unique /mcp et l'en-tête avec la clé réelle", () => {
    const endpoint = `${window.location.origin}/mcp`;
    renderPanel({ apiKey: "sk-secret-123" });

    // Endpoint unique = origin + /mcp (pas de workspace dans l'URL)
    expect(screen.getByText(endpoint)).toBeInTheDocument();
    // En-tête d'auth avec la vraie clé
    expect(screen.getByText("Authorization: Bearer sk-secret-123")).toBeInTheDocument();
    // Le bloc mcpServers contient un unique serveur ragflow avec l'URL et la clé
    const config = screen.getByText(/"mcpServers"/);
    expect(config.textContent).toContain('"ragflow"');
    expect(config.textContent).toContain(endpoint);
    expect(config.textContent).toContain("Bearer sk-secret-123");
    // Pas d'URL par workspace
    expect(config.textContent).not.toContain(`${endpoint}/`);
  });

  it("affiche la note pédagogique sur list_workspaces", () => {
    renderPanel({ apiKey: "k" });
    expect(screen.getByText(/list_workspaces/)).toBeInTheDocument();
  });

  it("sans clé, utilise un placeholder et affiche la note", () => {
    renderPanel({});

    expect(screen.getByText("Authorization: Bearer <VOTRE_CLÉ_API>")).toBeInTheDocument();
    expect(screen.getByText(/remplacez <VOTRE_CLÉ_API>/)).toBeInTheDocument();
  });
});
