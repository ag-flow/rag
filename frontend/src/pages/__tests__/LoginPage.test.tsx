import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frLogin from "@/i18n/fr/login.json";
import enLogin from "@/i18n/en/login.json";

import { LoginPage } from "@/pages/LoginPage";
import { useAuthMethods, type AuthMethods } from "@/hooks/useAuthMethods";

vi.mock("@/hooks/useAuthMethods", () => ({
  useAuthMethods: vi.fn(),
}));

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["login"],
    defaultNS: "login",
    resources: {
      fr: { login: frLogin },
      en: { login: enLogin },
    },
    interpolation: { escapeValue: false },
  });
});

type LocationLike = { href: string; pathname: string; search: string };
let locationStub: LocationLike;

beforeEach(() => {
  locationStub = { href: "", pathname: "/ui/login", search: "" };
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: locationStub,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockMethods(methods: AuthMethods | undefined, isLoading = false) {
  vi.mocked(useAuthMethods).mockReturnValue({
    data: methods,
    isLoading,
  } as unknown as ReturnType<typeof useAuthMethods>);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <LoginPage />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("LoginPage", () => {
  it("state 1 (oidc=true, bootstrap=true) → bouton SSO + formulaire visibles", () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: true });
    renderPage();
    expect(screen.getByRole("button", { name: /Keycloak/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
  });

  it("state 2 (oidc=false, bootstrap=true) → formulaire seul + message info", () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: true });
    renderPage();
    expect(screen.queryByRole("button", { name: /Keycloak/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    expect(screen.getByText(/OIDC pas encore configuré/i)).toBeInTheDocument();
  });

  it("state 3 (oidc=true, bootstrap=false) → SSO seul, pas de form", () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: false });
    renderPage();
    expect(screen.getByRole("button", { name: /Keycloak/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Username/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Password/i)).not.toBeInTheDocument();
  });

  it("state 4 (oidc=false, bootstrap=false) → message d'erreur 'no_method'", () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: false });
    renderPage();
    expect(screen.getByText(/Aucune méthode d'authentification/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Keycloak/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Username/i)).not.toBeInTheDocument();
  });

  it("submit valide → POST /auth/local/login puis redirect vers /ui + next", async () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: true });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/auth/local/login");
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(init.body)).toEqual({ username: "admin", password: "s3cret" });

    await waitFor(() => expect(locationStub.href).toBe("/ui/workspaces"));
  });

  it("submit retourne 401 → erreur visible, pas de redirect", async () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: true });
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(screen.getByText(/Identifiants invalides/i)).toBeInTheDocument());
    expect(locationStub.href).toBe("");
  });

  it("clic sur le bouton SSO → redirect vers /auth/login?next=...", () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: false });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Keycloak/i }));
    expect(locationStub.href).toBe(`/auth/login?next=${encodeURIComponent("/ui/workspaces")}`);
  });
});
