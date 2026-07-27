import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frLogin from "@/i18n/fr/login.json";
import enLogin from "@/i18n/en/login.json";

import { LoginPage } from "@/pages/LoginPage";
import { useAuthMethods, type AuthMethods } from "@/hooks/useAuthMethods";
import { usePublicStats, useVersionInfo } from "@/hooks/usePublicInfo";

vi.mock("@/hooks/useAuthMethods", () => ({
  useAuthMethods: vi.fn(),
}));
vi.mock("@/hooks/usePublicInfo", () => ({
  usePublicStats: vi.fn(),
  useVersionInfo: vi.fn(),
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
  mockStats({ indexed_documents: 1234, workspaces: 7 });
  vi.mocked(useVersionInfo).mockReturnValue({
    data: { version: "2.14", git: "abc123", environment: "prod" },
  } as unknown as ReturnType<typeof useVersionInfo>);
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: _origLocation,
  });
});

const DEFAULT_METHODS: AuthMethods = {
  oidc_configured: false,
  local_auth_enabled: false,
  needs_setup: false,
  local_auth_disabled_by_config: false,
};

function mockMethods(methods: Partial<AuthMethods> | undefined, isLoading = false) {
  vi.mocked(useAuthMethods).mockReturnValue({
    data: methods ? { ...DEFAULT_METHODS, ...methods } : undefined,
    isLoading,
  } as unknown as ReturnType<typeof useAuthMethods>);
}

function mockStats(stats: { indexed_documents: number | null; workspaces: number | null } | null) {
  vi.mocked(usePublicStats).mockReturnValue({
    data: stats,
  } as unknown as ReturnType<typeof usePublicStats>);
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
    expect(screen.queryByRole("button", { name: /OIDC/i })).not.toBeInTheDocument();
  });

  it("oidc=true, local=true → local en premier (primaire), OIDC en secondaire", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.getByRole("button", { name: /OIDC/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Identifiant/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Mot de passe/i)).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    const submitIdx = buttons.findIndex((b) => /Se connecter/i.test(b.textContent ?? ""));
    const oidcIdx = buttons.findIndex((b) => /OIDC/i.test(b.textContent ?? ""));
    expect(submitIdx).toBeLessThan(oidcIdx);
  });

  it("oidc=false, local=true → formulaire login seul + message info", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.queryByRole("button", { name: /OIDC/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Identifiant/i)).toBeInTheDocument();
    expect(screen.getByText(/OIDC pas encore configuré/i)).toBeInTheDocument();
  });

  it("oidc=true, local=false → SSO seul, pas de form login", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: false, needs_setup: false });
    renderPage();
    expect(screen.getByRole("button", { name: /OIDC/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Identifiant/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Mot de passe/i)).not.toBeInTheDocument();
  });

  it("liens GitHub et Contrats API, sur le login ET le wizard setup", () => {
    mockMethods({ oidc_configured: true, local_auth_enabled: true, needs_setup: false });
    const { unmount } = renderPage();
    expect(screen.getByRole("link", { name: /Contrats API/i })).toHaveAttribute("href", "/docs");
    expect(screen.getByRole("link", { name: /GitHub/i })).toHaveAttribute(
      "href",
      "https://github.com/ag-flow/rag",
    );
    unmount();

    mockMethods({ oidc_configured: false, local_auth_enabled: false, needs_setup: true });
    renderPage();
    expect(screen.getByRole("link", { name: /Contrats API/i })).toHaveAttribute("href", "/docs");
  });

  it("oidc=false, local=false → message d'erreur 'no_method'", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: false, needs_setup: false });
    renderPage();
    expect(screen.getByText(/Aucune méthode d'authentification/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /OIDC/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Identifiant/i)).not.toBeInTheDocument();
  });

  it("panneau de présentation : métriques servies par l'API", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.getByText(/Toute la chaîne RAG/i)).toBeInTheDocument();
    expect(screen.getByText((1234).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("métriques indisponibles → cellules vides, pas d'erreur bloquante", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    mockStats(null);
    renderPage();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByLabelText(/Identifiant/i)).toBeInTheDocument();
  });

  it("champs vides → messages d'erreur, aucune requête", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));
    await waitFor(() => expect(screen.getAllByText(/Champ requis/i)).toHaveLength(2));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lien setup absent hors premier démarrage", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.queryByText(/Premier démarrage/i)).not.toBeInTheDocument();
  });

  it("pied de page : version, environnement et bascule de langue", () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    renderPage();
    expect(screen.getByText(/api 2\.14/i)).toBeInTheDocument();
    expect(screen.getByText("prod")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "en" })).toBeInTheDocument();
  });

  it("submit login valide → POST /auth/local/login puis redirect vers /ui/workspaces", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Identifiant/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Mot de passe/i), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/auth/local/login");
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(init.body)).toEqual({ username: "admin", password: "s3cret" });

    await waitFor(() => expect(locationStub.href).toBe("/ui/workspaces"));
  });

  it("submit login retourne 401 → erreur visible, effacée à la saisie", async () => {
    mockMethods({ oidc_configured: false, local_auth_enabled: true, needs_setup: false });
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText(/Identifiant/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Mot de passe/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/i }));

    await waitFor(() => expect(screen.getByText(/Identifiants invalides/i)).toBeInTheDocument());
    expect(locationStub.href).toBe("");

    fireEvent.change(screen.getByLabelText(/Mot de passe/i), { target: { value: "retry" } });
    await waitFor(() =>
      expect(screen.queryByText(/Identifiants invalides/i)).not.toBeInTheDocument(),
    );
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
    fireEvent.click(screen.getByRole("button", { name: /OIDC/i }));
    expect(locationStub.href).toBe(`/auth/login?next=${encodeURIComponent("/ui/workspaces")}`);
  });
});
