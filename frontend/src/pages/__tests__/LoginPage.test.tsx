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
const _origLocation = window.location;

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
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: _origLocation,
  });
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
  it("needs_setup=true → formulaire de création admin", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: false, needs_setup: true });
    renderPage();
    expect(screen.getByText(/Créer le compte administrateur/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Adresse e-mail/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Keycloak/i })).not.toBeInTheDocument();
  });

  it("oidc=true, local=true → bouton SSO + formulaire login visibles", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.getByRole("button", { name: /Keycloak/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
  });

  it("oidc=false, local=true → formulaire login seul + message info", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.queryByRole("button", { name: /Keycloak/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    expect(screen.getByText(/OIDC pas encore configuré/i)).toBeInTheDocument();
  });

  it("oidc=true, local=false → SSO seul, pas de form login", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: false, needs_setup: false });
    renderPage();
    expect(screen.getByRole("button", { name: /Keycloak/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Username/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Password/i)).not.toBeInTheDocument();
  });

  it("oidc=false, local=false → message d'erreur 'no_method'", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: false, needs_setup: false });
    renderPage();
    expect(screen.getByText(/Aucune méthode d'authentification/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Keycloak/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Username/i)).not.toBeInTheDocument();
  });

  it("submit login valide → POST /auth/local/login puis redirect vers /ui/workspaces", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/auth/local/login");
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(init.body)).toEqual({ username: "admin", password: "s3cret" });

    await waitFor(() => expect(locationStub.href).toBe("/ui/workspaces"));
  });

  it("submit login retourne 401 → erreur visible, pas de redirect", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(screen.getByText(/Identifiants invalides/i)).toBeInTheDocument());
    expect(locationStub.href).toBe("");
  });

  it("submit wizard setup → POST /api/setup/init-admin puis redirect", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: false, needs_setup: true });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Nom d'utilisateur/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Adresse e-mail/i), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^Mot de passe$/i), { target: { value: "secret123" } });
    fireEvent.change(screen.getByLabelText(/Confirmer/i), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: /Créer le compte/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/setup/init-admin");
    expect(init).toMatchObject({ method: "POST" });
    const body = JSON.parse(init.body);
    expect(body).toEqual({
      username: "admin",
      email: "admin@example.com",
      password: "secret123",
    });

    await waitFor(() => expect(locationStub.href).toBe("/ui/workspaces"));
  });

  it("clic SSO → redirect vers /auth/login?next=...", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: false, needs_setup: false });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Keycloak/i }));
    expect(locationStub.href).toBe(`/auth/login?next=${encodeURIComponent("/ui/workspaces")}`);
  });
});
