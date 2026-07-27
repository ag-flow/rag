import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import { DefaultStrategyPanel } from "@/pages/workspace/DefaultStrategyPanel";
import { useSetDefaultStrategy } from "@/hooks/useChunking";

const setDefaultMutate = vi.fn();

vi.mock("@/hooks/useChunking", () => ({
  useSetDefaultStrategy: vi.fn(() => ({ mutate: setDefaultMutate, isPending: false })),
}));
vi.mock("@/hooks/useChunkingStrategies", () => ({
  useChunkingStrategies: () => ({
    data: [
      {
        id: "00000000-0000-0000-0000-000000000001",
        label: "markdown-deep",
        slug: "markdown-deep",
        algo: "prose",
        params: {},
        parser_slug: null,
        is_system: true,
        used_by_routes: 0,
        used_by_categories: 1,
        used_by_triggers: 0,
        used_by_workspaces: 0,
        created_at: "",
        updated_at: "",
      },
    ],
    isLoading: false,
  }),
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

describe("DefaultStrategyPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("désactive Appliquer tant que la sélection n'a pas changé", () => {
    renderWithProviders(<DefaultStrategyPanel workspaceName="ws" defaultStrategyId={null} />);
    expect(screen.getByRole("button", { name: "Appliquer" })).toBeDisabled();
  });

  it("applique le binding par id après sélection d'une stratégie", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DefaultStrategyPanel workspaceName="ws" defaultStrategyId={null} />);

    await user.click(screen.getByRole("combobox", { name: "Stratégie du catalogue" }));
    await user.click(screen.getByRole("option", { name: "markdown-deep" }));
    await user.click(screen.getByRole("button", { name: "Appliquer" }));

    expect(setDefaultMutate).toHaveBeenCalledWith(
      { strategyId: "00000000-0000-0000-0000-000000000001", confirm: false },
      expect.anything(),
    );
    expect(vi.mocked(useSetDefaultStrategy)).toHaveBeenCalledWith("ws");
  });
});
