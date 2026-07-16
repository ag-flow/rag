import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import * as apiModule from "@/lib/api";
import { ApiKeysPage } from "@/pages/ApiKeysPage";
import type { UserApiKey } from "@/lib/user-api-keys.types";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const KEY: UserApiKey = {
  id: "k-1",
  name: "claude-code",
  fingerprint_preview: "a3f2c1d4",
  status: "active",
  created_at: "2026-07-01T00:00:00Z",
  revoked_at: null,
  rotated_at: null,
  workspaces: [
    {
      workspace_id: "w-1",
      workspace_name: "mon-projet",
      can_read: true,
      can_write: false,
    },
  ],
};

describe("ApiKeysPage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("liste les clés avec leurs grants et permissions", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([KEY]);
    render(
      <Wrapper>
        <ApiKeysPage />
      </Wrapper>,
    );

    expect(await screen.findByText("claude-code")).toBeInTheDocument();
    expect(screen.getByText("mon-projet (R)")).toBeInTheDocument();
    expect(screen.getByText(/^Active$/)).toBeInTheDocument();
  });

  it("affiche l'état vide", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);
    render(
      <Wrapper>
        <ApiKeysPage />
      </Wrapper>,
    );
    expect(await screen.findByText(/Aucune clé API/)).toBeInTheDocument();
  });

  it("révoque une clé après confirmation", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([KEY]);
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockResolvedValue(undefined);

    render(
      <Wrapper>
        <ApiKeysPage />
      </Wrapper>,
    );
    await screen.findByText("claude-code");

    fireEvent.click(screen.getByRole("button", { name: /Révoquer/i }));
    // AlertDialog de confirmation
    fireEvent.click(await screen.findByRole("button", { name: /^Révoquer$/i }));

    await waitFor(() =>
      expect(deleteSpy).toHaveBeenCalledWith("/api/me/api-keys/k-1"),
    );
  });

  it("crée une clé et affiche la valeur une seule fois", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);
    const postSpy = vi.spyOn(apiModule.api, "post").mockResolvedValue({
      id: "k-2",
      name: "nouvelle",
      api_key: "ws_secret_value_once",
      fingerprint_preview: "deadbeef",
      created_at: "2026-07-16T00:00:00Z",
    });

    render(
      <Wrapper>
        <ApiKeysPage />
      </Wrapper>,
    );
    await screen.findByText(/Aucune clé API/);

    fireEvent.click(screen.getByRole("button", { name: /Créer une clé/i }));
    const nameInput = await screen.findByPlaceholderText(/claude-code, ci-cd/);
    fireEvent.change(nameInput, { target: { value: "nouvelle" } });
    fireEvent.click(screen.getByRole("button", { name: /^Créer$/i }));

    // La clé est affichée une fois (panneau show-once)
    expect(await screen.findByDisplayValue("ws_secret_value_once")).toBeInTheDocument();
    expect(postSpy).toHaveBeenCalledWith("/api/me/api-keys", {
      name: "nouvelle",
      workspaces: [],
    });
  });
});
