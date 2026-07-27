import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frOidc from "@/i18n/fr/oidc.json";
import enOidc from "@/i18n/en/oidc.json";

import { OidcConfigPage } from "@/pages/OidcConfigPage";

const mutateMock = vi.fn();
const setSecretMutate = vi.fn();
const setLocalMutate = vi.fn();
const setPublicUrlMutate = vi.fn();

vi.mock("@/hooks/useOidcConfig", () => ({
  useOidcConfig: vi.fn(),
  useUpsertOidcConfig: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@/hooks/useAdminAuthConfig", () => ({
  useClientSecretStatus: vi.fn(),
  useSetClientSecret: () => ({ mutate: setSecretMutate, isPending: false }),
  useLocalLogin: vi.fn(),
  useSetLocalLogin: () => ({ mutate: setLocalMutate, isPending: false }),
  usePublicUrl: vi.fn(),
  useSetPublicUrl: () => ({ mutate: setPublicUrlMutate, isPending: false }),
}));

import { useOidcConfig } from "@/hooks/useOidcConfig";
import { useClientSecretStatus, useLocalLogin, usePublicUrl } from "@/hooks/useAdminAuthConfig";

function mockSecretStatus(configured: boolean): void {
  vi.mocked(useClientSecretStatus).mockReturnValue({
    data: { configured },
  } as unknown as ReturnType<typeof useClientSecretStatus>);
}

function mockLocalLogin(enabled: boolean): void {
  vi.mocked(useLocalLogin).mockReturnValue({
    data: { enabled },
  } as unknown as ReturnType<typeof useLocalLogin>);
}

function mockPublicUrl(value: string | null): void {
  vi.mocked(usePublicUrl).mockReturnValue({
    data: { value },
  } as unknown as ReturnType<typeof usePublicUrl>);
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

function mockConfig(data: unknown): void {
  vi.mocked(useOidcConfig).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useOidcConfig>);
}

describe("OidcConfigPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSecretStatus(false);
    mockLocalLogin(true);
    mockPublicUrl(null);
    mockConfig(null);
  });

  it("URL publique : badge Automatique quand vide, saisie appelle setPublicUrl", () => {
    renderPage();
    expect(screen.getByText("Automatique (adresse d'appel du client)")).toBeInTheDocument();

    const input = screen.getByRole("textbox", { name: "URL publique de l'application" });
    fireEvent.change(input, { target: { value: "https://rag.yoops.org" } });
    const section = input.closest("section");
    expect(section).not.toBeNull();
    fireEvent.click(within(section as HTMLElement).getByRole("button", { name: "Enregistrer" }));
    expect(setPublicUrlMutate).toHaveBeenCalledWith("https://rag.yoops.org", expect.anything());
  });

  it("URL publique : valeur configurée pré-remplie, pas de badge Automatique", () => {
    mockPublicUrl("https://rag.yoops.org");
    renderPage();
    const input = screen.getByRole("textbox", { name: "URL publique de l'application" });
    expect((input as HTMLInputElement).value).toBe("https://rag.yoops.org");
    expect(screen.queryByText("Automatique (adresse d'appel du client)")).not.toBeInTheDocument();
  });

  it("form vide si pas de config", () => {
    renderPage();
    const inputs = screen.getAllByRole("textbox");
    inputs.forEach((input) => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("form pré-rempli si config existante", () => {
    mockConfig({ issuer: "https://kc.example.com/realms/test", client_id: "rag" });
    renderPage();
    expect(screen.getByDisplayValue("https://kc.example.com/realms/test")).toBeInTheDocument();
    expect(screen.getByDisplayValue("rag")).toBeInTheDocument();
  });

  it("submit issuer/client_id appelle upsert.mutate", async () => {
    renderPage();
    const [issuerInput, clientIdInput] = screen.getAllByRole("textbox");
    if (!issuerInput || !clientIdInput) {
      throw new Error("Expected 2 textbox inputs on the OIDC form");
    }
    fireEvent.change(issuerInput, { target: { value: "https://kc.example.com/realms/test" } });
    fireEvent.change(clientIdInput, { target: { value: "rag" } });
    const oidcForm = issuerInput.closest("form");
    if (!oidcForm) throw new Error("form OIDC introuvable");
    fireEvent.click(within(oidcForm).getByRole("button", { name: /^Enregistrer$/i }));
    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    expect(mutateMock.mock.calls[0]?.[0]).toEqual({
      issuer: "https://kc.example.com/realms/test",
      client_id: "rag",
    });
  });

  it("client secret : statut Non défini quand absent", () => {
    mockSecretStatus(false);
    renderPage();
    expect(screen.getByText(/^Non défini$/)).toBeInTheDocument();
  });

  it("client secret : statut Défini quand présent", () => {
    mockSecretStatus(true);
    renderPage();
    expect(screen.getByText(/^Défini$/)).toBeInTheDocument();
  });

  it("saisie + enregistrement du client secret appelle la mutation", () => {
    renderPage();
    const section = screen.getByText("Client secret").closest("section");
    if (!section) throw new Error("section client secret introuvable");
    const input = screen.getByPlaceholderText(/Coller le client secret/);
    fireEvent.change(input, { target: { value: "hrpv_secret_abc" } });
    fireEvent.click(within(section).getByRole("button", { name: /Enregistrer/i }));
    expect(setSecretMutate.mock.calls[0]?.[0]).toBe("hrpv_secret_abc");
  });

  it("toggle connexion locale : reflète l'état et bascule", () => {
    mockLocalLogin(true);
    renderPage();
    const sw = screen.getByRole("switch");
    expect(sw).toBeChecked();
    fireEvent.click(sw);
    expect(setLocalMutate.mock.calls[0]?.[0]).toBe(false);
  });

  it("rend la procédure de création de client Keycloak", () => {
    renderPage();
    expect(screen.getByText(/Créer un Client ID \(Keycloak\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/\/auth\/callback/).length).toBeGreaterThan(0);
  });
});
