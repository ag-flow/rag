import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceWebhooksTab } from "@/pages/workspace/WorkspaceWebhooksTab";

const { mockListWebhooks } = vi.hoisted(() => ({
  mockListWebhooks: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/lib/webhooks", () => ({
  listWebhooks: mockListWebhooks,
  createWebhook: vi.fn(),
  patchWebhook: vi.fn(),
  deleteWebhook: vi.fn(),
  listWebhookCalls: vi.fn().mockResolvedValue([]),
  purgeWebhookCalls: vi.fn(),
}));

describe("WorkspaceWebhooksTab", () => {
  beforeEach(() => {
    mockListWebhooks.mockResolvedValue([]);
  });

  it("affiche l'état vide quand aucun webhook n'est configuré", async () => {
    renderWithProviders(<WorkspaceWebhooksTab workspaceName="ws1" />);
    expect(
      await screen.findByText("Aucun webhook configuré."),
    ).toBeInTheDocument();
  });

  it("affiche les onglets Webhooks et Audit log", async () => {
    renderWithProviders(<WorkspaceWebhooksTab workspaceName="ws1" />);
    expect(await screen.findByText("Webhooks")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });

  it("affiche le bouton Ajouter sur l'onglet liste", async () => {
    renderWithProviders(<WorkspaceWebhooksTab workspaceName="ws1" />);
    expect(await screen.findByText("Ajouter")).toBeInTheDocument();
  });

  it("affiche les webhooks quand la liste n'est pas vide", async () => {
    mockListWebhooks.mockResolvedValue([
      {
        id: "wh-1",
        name: "mon-webhook",
        url: "https://example.com/hook",
        enabled: true,
        headers: [],
      },
    ]);
    renderWithProviders(<WorkspaceWebhooksTab workspaceName="ws1" />);
    expect(await screen.findByText("mon-webhook")).toBeInTheDocument();
  });
});
