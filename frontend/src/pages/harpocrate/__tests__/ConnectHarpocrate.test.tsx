import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { renderWithProviders, testI18n } from "../../workspace/__tests__/testUtils";
import { CreateVaultDialog } from "@/pages/harpocrate/CreateVaultDialog";
import { useConnectReturn } from "@/pages/harpocrate/useConnectReturn";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/harpocrate-vaults", () => ({
  harpocrateVaultsApi: { connectStart: vi.fn(), create: vi.fn() },
}));
const { toastSpy } = vi.hoisted(() => ({ toastSpy: vi.fn() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: toastSpy }) }));

import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";

const connectStart = vi.mocked(harpocrateVaultsApi.connectStart);
const assignSpy = vi.fn();

function fillIdentity(baseUrl = "https://vault.example") {
  fireEvent.change(screen.getByPlaceholderText("rag, prod-eu, staging…"), {
    target: { value: "rag-connect" },
  });
  fireEvent.change(screen.getByPlaceholderText("Coffre RAG production"), {
    target: { value: "Coffre connecté" },
  });
  fireEvent.change(screen.getByPlaceholderText("https://vault.yoops.org"), {
    target: { value: baseUrl },
  });
}

function openDialog(isFirstVault = false) {
  renderWithProviders(
    <CreateVaultDialog
      open={true}
      onOpenChange={() => {}}
      onCreated={() => {}}
      isFirstVault={isFirstVault}
    />,
  );
}

describe("CreateVaultDialog — Connecter à Harpocrate", () => {
  beforeEach(() => {
    connectStart.mockReset();
    toastSpy.mockReset();
    assignSpy.mockReset();
    vi.stubGlobal("location", { ...window.location, assign: assignSpy });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("part chez Harpocrate avec nom, libellé et URL — sans api_key", async () => {
    connectStart.mockResolvedValue({ browser_url: "https://vault.example/connect?x=1" });
    openDialog();
    fillIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Connecter à Harpocrate/ }));

    await waitFor(() =>
      expect(assignSpy).toHaveBeenCalledWith("https://vault.example/connect?x=1"),
    );
    expect(connectStart).toHaveBeenCalledWith({
      name: "rag-connect",
      label: "Coffre connecté",
      base_url: "https://vault.example",
      // Un coffre existe déjà : le nouveau ne lui vole pas le statut par défaut.
      is_default: false,
    });
  });

  it("coche « par défaut » d'office uniquement pour le premier coffre", () => {
    openDialog(true);
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("avertit qu'un nouveau coffre par défaut retire ce statut à l'actuel", () => {
    openDialog(false);
    const box = screen.getByRole("checkbox");
    expect(box).not.toBeChecked();
    fireEvent.click(box);
    expect(screen.getByRole("note")).toHaveTextContent(/perdra ce statut/);
  });

  it("ne part pas tant que le nom et l'URL ne sont pas valides", async () => {
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /Connecter à Harpocrate/ }));
    await waitFor(() => expect(screen.getAllByText(/Libellé requis/).length).toBeGreaterThan(0));
    expect(connectStart).not.toHaveBeenCalled();
  });

  it("explique une application non déclarée et affiche quoi déclarer", async () => {
    connectStart.mockRejectedValue(
      new ApiError(409, {
        detail: {
          reason: "client_not_declared",
          client_id: "ragflow",
          redirect_uri: "https://rag.example/api/admin/harpocrate-vaults/connect/callback",
        },
      }),
    );
    openDialog();
    fillIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Connecter à Harpocrate/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/ne connaît pas l'application/);
    expect(screen.getByText("ragflow")).toBeInTheDocument();
    expect(
      screen.getByText("https://rag.example/api/admin/harpocrate-vaults/connect/callback"),
    ).toBeInTheDocument();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

function ReturnProbe() {
  useConnectReturn();
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
}

function renderReturn(search: string) {
  const qc = new QueryClient();
  render(
    <MemoryRouter initialEntries={[`/settings/harpocrate-vaults${search}`]}>
      <I18nextProvider i18n={testI18n}>
        <QueryClientProvider client={qc}>
          <ReturnProbe />
        </QueryClientProvider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}

describe("useConnectReturn — retour de Harpocrate", () => {
  beforeEach(() => toastSpy.mockReset());

  it("annonce le coffre créé puis ne garde que la sélection du coffre", async () => {
    renderReturn("?connect=ok&vault=v-1&tested=true");
    await waitFor(() => expect(screen.getByTestId("search")).toHaveTextContent("?vault=v-1"));
    expect(toastSpy).toHaveBeenCalledWith({ title: "Coffre créé et connecté à Harpocrate." });
  });

  it("traduit une raison connue et neutralise une raison inconnue", async () => {
    renderReturn("?connect_error=denied");
    await waitFor(() => expect(toastSpy).toHaveBeenCalledTimes(1));
    expect(toastSpy.mock.calls[0]?.[0].title).toMatch(/Connexion refusée/);

    toastSpy.mockReset();
    renderReturn("?connect_error=<script>");
    await waitFor(() => expect(toastSpy).toHaveBeenCalledTimes(1));
    expect(toastSpy.mock.calls[0]?.[0].title).toBe("La connexion à Harpocrate a échoué.");
  });
});
