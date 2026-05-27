import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import { WorkspacesPage } from "@/pages/WorkspacesPage";

import frCommon from "@/i18n/fr/common.json";
import frWorkspace from "@/i18n/fr/workspace.json";
import frWorkspaces from "@/i18n/fr/workspaces.json";
import enCommon from "@/i18n/en/common.json";
import enWorkspace from "@/i18n/en/workspace.json";
import enWorkspaces from "@/i18n/en/workspaces.json";

const pageI18n = i18next.createInstance();
void pageI18n.use(initReactI18next).init({
  lng: "fr",
  fallbackLng: "fr",
  ns: ["common", "workspace", "workspaces"],
  defaultNS: "common",
  resources: {
    fr: { common: frCommon, workspace: frWorkspace, workspaces: frWorkspaces },
    en: { common: enCommon, workspace: enWorkspace, workspaces: enWorkspaces },
  },
  interpolation: { escapeValue: false },
});

// Mock react-router-dom's useSearchParams
const mockSetSearchParams = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useSearchParams: () => [mockSearchParams, mockSetSearchParams],
    useNavigate: () => vi.fn(),
  };
});

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaces: () => ({ data: [], isLoading: false }),
  useWorkspace: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("@/pages/workspace/CreateWorkspaceDialog", () => ({
  CreateWorkspaceDialog: () => null,
}));

vi.mock("@/pages/workspace/WorkspaceDetailPanel", () => ({
  WorkspaceDetailPanel: ({ name }: { name: string }) => (
    <div data-testid="detail-panel">{name}</div>
  ),
}));

function renderPage(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <I18nextProvider i18n={pageI18n}>
        <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}

describe("WorkspacesPage", () => {
  it("affiche l'état vide quand aucun workspace", () => {
    mockSearchParams = new URLSearchParams();
    renderPage(<WorkspacesPage />);
    expect(screen.getByText("Aucun workspace")).toBeInTheDocument();
  });

  it("setSearchParams est une fonction disponible", () => {
    mockSearchParams = new URLSearchParams();
    // Vérifie que le mock est en place
    expect(typeof mockSetSearchParams).toBe("function");
  });

  it("ne crashe pas si un ws est déjà dans l'URL", () => {
    mockSearchParams = new URLSearchParams({ ws: "some-ws" });
    renderPage(<WorkspacesPage />);
    // La page charge sans erreur (état vide avec data:[])
    expect(screen.getByText("Aucun workspace")).toBeInTheDocument();
  });
});
