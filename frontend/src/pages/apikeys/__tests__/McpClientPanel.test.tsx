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

const WS = { workspace_id: "ws-uuid-1", workspace_name: "docs", can_read: true };

describe("McpClientPanel", () => {
  it("construit l'endpoint et l'en-tête avec la clé réelle", () => {
    const endpoint = `${window.location.origin}/mcp/ws-uuid-1`;
    renderPanel({ grants: [WS], apiKey: "sk-secret-123" });

    // Endpoint = origin + /mcp/{workspace_id}
    expect(screen.getByText(endpoint)).toBeInTheDocument();
    // En-tête d'auth avec la vraie clé
    expect(screen.getByText("Authorization: Bearer sk-secret-123")).toBeInTheDocument();
    // Le bloc mcpServers contient l'URL et la clé
    const config = screen.getByText(/"mcpServers"/);
    expect(config.textContent).toContain(endpoint);
    expect(config.textContent).toContain("Bearer sk-secret-123");
  });

  it("sans clé, utilise un placeholder et affiche la note", () => {
    renderPanel({ grants: [WS] });

    expect(screen.getByText("Authorization: Bearer <VOTRE_CLÉ_API>")).toBeInTheDocument();
    expect(screen.getByText(/remplacez <VOTRE_CLÉ_API>/)).toBeInTheDocument();
  });

  it("n'expose que les workspaces en lecture", () => {
    renderPanel({
      grants: [WS, { workspace_id: "ws-2", workspace_name: "private", can_read: false }],
      apiKey: "k",
    });

    expect(
      screen.getByText(`${window.location.origin}/mcp/ws-uuid-1`),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(`${window.location.origin}/mcp/ws-2`),
    ).not.toBeInTheDocument();
  });

  it("aucun grant lecture → message d'aide, pas d'endpoint", () => {
    renderPanel({
      grants: [{ workspace_id: "ws-2", workspace_name: "private", can_read: false }],
      apiKey: "k",
    });

    expect(screen.getByText(/exige le grant/)).toBeInTheDocument();
    expect(screen.queryByText(/Authorization: Bearer/)).not.toBeInTheDocument();
  });
});
