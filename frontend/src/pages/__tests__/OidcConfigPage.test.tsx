import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frOidc from "@/i18n/fr/oidc.json";
import enOidc from "@/i18n/en/oidc.json";

import { OidcConfigPage } from "@/pages/OidcConfigPage";

const mutateMock = vi.fn();

vi.mock("@/hooks/useOidcConfig", () => ({
  useOidcConfig: vi.fn(),
  useUpsertOidcConfig: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@/hooks/useAuthMethods", () => ({
  useAuthMethods: vi.fn(),
}));

import { useOidcConfig } from "@/hooks/useOidcConfig";
import { useAuthMethods } from "@/hooks/useAuthMethods";

function mockAuthMethods(localDisabled: boolean): void {
  vi.mocked(useAuthMethods).mockReturnValue({
    data: {
      oidc_configured: true,
      local_auth_enabled: !localDisabled,
      needs_setup: false,
      local_auth_disabled_by_config: localDisabled,
    },
  } as unknown as ReturnType<typeof useAuthMethods>);
}

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["oidc"],
    defaultNS: "oidc",
    resources: {
      fr: { oidc: frOidc },
      en: { oidc: enOidc },
    },
    interpolation: { escapeValue: false },
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <OidcConfigPage />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("OidcConfigPage", () => {
  beforeEach(() => {
    mockAuthMethods(false);
  });

  it("form vide si pas de config", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const inputs = screen.getAllByRole("textbox");
    inputs.forEach((input) => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("form pré-rempli si config existante", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: {
        issuer: "https://kc.example.com/realms/test",
        client_id: "rag",
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByDisplayValue("https://kc.example.com/realms/test")).toBeInTheDocument();
    expect(screen.getByDisplayValue("rag")).toBeInTheDocument();
  });

  it("Save désactivé tant que non-dirty", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: {
        issuer: "https://kc.example.com/realms/test",
        client_id: "rag",
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const save = screen.getByText(/^Enregistrer$/i).closest("button");
    expect(save).toBeDisabled();
  });

  it("submit avec valeurs valides appelle upsert.mutate", async () => {
    mutateMock.mockClear();
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const inputs = screen.getAllByRole("textbox");
    const [issuerInput, clientIdInput] = inputs;
    if (!issuerInput || !clientIdInput) {
      throw new Error("Expected 2 textbox inputs on the OIDC form");
    }
    fireEvent.change(issuerInput, { target: { value: "https://kc.example.com/realms/test" } });
    fireEvent.change(clientIdInput, { target: { value: "rag" } });
    fireEvent.click(screen.getByText(/^Enregistrer$/i));
    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    expect(mutateMock.mock.calls[0]?.[0]).toEqual({
      issuer: "https://kc.example.com/realms/test",
      client_id: "rag",
    });
  });

  it("affiche le statut connexion locale = Activée quand le flag est off", () => {
    mockAuthMethods(false);
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByText(/^Activée$/)).toBeInTheDocument();
  });

  it("affiche le statut connexion locale = Désactivée quand le flag est on", () => {
    mockAuthMethods(true);
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByText(/^Désactivée$/)).toBeInTheDocument();
    expect(screen.getAllByText(/RAG_LOCAL_AUTH_DISABLED=false/).length).toBeGreaterThan(0);
  });

  it("rend la procédure de création de client Keycloak", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByText(/Créer un Client ID \(Keycloak\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/\/auth\/callback/).length).toBeGreaterThan(0);
  });
});
