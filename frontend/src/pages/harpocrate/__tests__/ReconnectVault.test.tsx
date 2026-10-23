import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { renderWithProviders, testI18n } from "../../workspace/__tests__/testUtils";
import { ReconnectVaultDialog } from "@/pages/harpocrate/ReconnectVaultDialog";
import { ConfirmWalletChangeDialog } from "@/pages/harpocrate/ConfirmWalletChangeDialog";
import { useConnectReturn } from "@/pages/harpocrate/useConnectReturn";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/harpocrate-vaults", () => ({
  harpocrateVaultsApi: {
    reconnectStart: vi.fn(),
    getPendingReconnect: vi.fn(),
    confirmReconnect: vi.fn(),
    cancelReconnect: vi.fn(),
  },
}));
const { toastSpy } = vi.hoisted(() => ({ toastSpy: vi.fn() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: toastSpy }) }));

import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";

const api = vi.mocked(harpocrateVaultsApi);
const assignSpy = vi.fn();
const PENDING = {
  request_id: "r-1",
  vault_id: "v-1",
  vault_name: "rag-existant",
  previous_wallet_id: "aaaaaaaa-0000-0000-0000-000000000001",
  new_wallet_id: "bbbbbbbb-0000-0000-0000-000000000002",
  expires_at: "2026-10-23T12:00:00Z",
};

describe("ReconnectVaultDialog — départ vers Harpocrate", () => {
  beforeEach(() => {
    api.reconnectStart.mockReset();
    assignSpy.mockReset();
    vi.stubGlobal("location", { ...window.location, assign: assignSpy });
  });
  afterEach(() => vi.unstubAllGlobals());

  function openDialog() {
    renderWithProviders(<ReconnectVaultDialog vaultId="v-1" open={true} onOpenChange={() => {}} />);
  }

  it("rappelle à qui appartiendra la clé puis part chez Harpocrate", async () => {
    api.reconnectStart.mockResolvedValue({ browser_url: "https://vault.example/connect?x=1" });
    openDialog();
    expect(screen.getByText(/appartiendra à VOTRE compte Harpocrate/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Continuer vers Harpocrate/ }));
    await waitFor(() =>
      expect(assignSpy).toHaveBeenCalledWith("https://vault.example/connect?x=1"),
    );
    expect(api.reconnectStart).toHaveBeenCalledWith("v-1");
  });

  it("affiche quoi déclarer quand Harpocrate ne connaît pas ragflow", async () => {
    api.reconnectStart.mockRejectedValue(
      new ApiError(409, {
        detail: {
          reason: "client_not_declared",
          client_id: "ragflow",
          redirect_uri: "https://r/cb",
        },
      }),
    );
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /Continuer vers Harpocrate/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/ne connaît pas l'application/);
    expect(screen.getByText("https://r/cb")).toBeInTheDocument();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});

describe("ConfirmWalletChangeDialog — changement de wallet", () => {
  const onDone = vi.fn();

  beforeEach(() => {
    toastSpy.mockReset();
    onDone.mockReset();
    api.getPendingReconnect.mockReset();
    api.confirmReconnect.mockReset();
    api.cancelReconnect.mockReset();
  });

  it("montre les deux wallets et remplace la clé sur confirmation", async () => {
    api.getPendingReconnect.mockResolvedValue(PENDING);
    api.confirmReconnect.mockResolvedValue({
      vault: { id: "v-1" } as never,
      tested: true,
    });
    renderWithProviders(<ConfirmWalletChangeDialog requestId="r-1" onDone={onDone} />);
    expect(await screen.findByText(PENDING.previous_wallet_id)).toBeInTheDocument();
    expect(screen.getByText(PENDING.new_wallet_id)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remplacer la clé" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(api.confirmReconnect).toHaveBeenCalledWith("r-1");
    expect(api.cancelReconnect).not.toHaveBeenCalled();
    expect(toastSpy).toHaveBeenCalledWith({
      title: "Clé du coffre remplacée par la nouvelle clé Harpocrate.",
    });
  });

  it("dit que le wallet actuel est inconnu quand la clé actuelle ne répond plus", async () => {
    api.getPendingReconnect.mockResolvedValue({ ...PENDING, previous_wallet_id: null });
    renderWithProviders(<ConfirmWalletChangeDialog requestId="r-1" onDone={onDone} />);
    expect(await screen.findByText(/la clé actuelle ne répond plus/)).toBeInTheDocument();
  });

  it("garde l'ancienne clé sur refus, sans rien confirmer", async () => {
    api.getPendingReconnect.mockResolvedValue(PENDING);
    api.cancelReconnect.mockResolvedValue(undefined);
    renderWithProviders(<ConfirmWalletChangeDialog requestId="r-1" onDone={onDone} />);
    await screen.findByText(PENDING.new_wallet_id);
    fireEvent.click(screen.getByRole("button", { name: "Garder l'ancienne clé" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(api.cancelReconnect).toHaveBeenCalledWith("r-1");
    expect(api.confirmReconnect).not.toHaveBeenCalled();
  });
});

function ReturnProbe() {
  const { pendingRequestId } = useConnectReturn();
  const location = useLocation();
  return (
    <>
      <div data-testid="search">{location.search}</div>
      <div data-testid="pending">{pendingRequestId ?? "none"}</div>
    </>
  );
}

function renderReturn(search: string) {
  render(
    <MemoryRouter initialEntries={[`/settings/harpocrate-vaults${search}`]}>
      <I18nextProvider i18n={testI18n}>
        <QueryClientProvider client={new QueryClient()}>
          <ReturnProbe />
        </QueryClientProvider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}

describe("useConnectReturn — retour d'une reconnexion", () => {
  beforeEach(() => toastSpy.mockReset());

  it("annonce la clé remplacée et garde la sélection du coffre", async () => {
    renderReturn("?connect=reconnected&vault=v-1&tested=true");
    await waitFor(() => expect(screen.getByTestId("search")).toHaveTextContent("?vault=v-1"));
    expect(toastSpy).toHaveBeenCalledWith({
      title: "Clé du coffre remplacée par la nouvelle clé Harpocrate.",
    });
    expect(screen.getByTestId("pending")).toHaveTextContent("none");
  });

  it("rend la demande à confirmer sans annoncer de remplacement", async () => {
    renderReturn("?connect=confirm_wallet&vault=v-1&request=r-1");
    await waitFor(() => expect(screen.getByTestId("pending")).toHaveTextContent("r-1"));
    expect(screen.getByTestId("search")).toHaveTextContent("?vault=v-1");
    expect(toastSpy).not.toHaveBeenCalled();
  });
});
