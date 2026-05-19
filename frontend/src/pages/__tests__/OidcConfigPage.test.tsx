import { describe, it, expect, vi, beforeAll } from "vitest";
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

import { useOidcConfig } from "@/hooks/useOidcConfig";

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
        client_secret_ref: "kc_rag_secret",
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByDisplayValue("https://kc.example.com/realms/test")).toBeInTheDocument();
    expect(screen.getByDisplayValue("rag")).toBeInTheDocument();
    expect(screen.getByDisplayValue("kc_rag_secret")).toBeInTheDocument();
  });

  it("Save désactivé tant que non-dirty", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: {
        issuer: "https://kc.example.com/realms/test",
        client_id: "rag",
        client_secret_ref: "kc_rag_secret",
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
    const [issuerInput, clientIdInput, clientSecretInput] = inputs;
    if (!issuerInput || !clientIdInput || !clientSecretInput) {
      throw new Error("Expected 3 textbox inputs on the OIDC form");
    }
    fireEvent.change(issuerInput, { target: { value: "https://kc.example.com/realms/test" } });
    fireEvent.change(clientIdInput, { target: { value: "rag" } });
    fireEvent.change(clientSecretInput, { target: { value: "kc_rag_secret" } });
    fireEvent.click(screen.getByText(/^Enregistrer$/i));
    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    expect(mutateMock.mock.calls[0]?.[0]).toEqual({
      issuer: "https://kc.example.com/realms/test",
      client_id: "rag",
      client_secret_ref: "kc_rag_secret",
    });
  });
});
