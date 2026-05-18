import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { DeleteRerankAlert } from "@/pages/workspace/DeleteRerankAlert";

const deleteMutate = vi.fn();
const toastMock = vi.fn();

vi.mock("@/hooks/useRerank", () => ({
  useDeleteRerankConfig: () => ({ mutate: deleteMutate, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

describe("DeleteRerankAlert", () => {
  it("ne rend rien quand open=false", () => {
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={false} onOpenChange={() => {}} />,
    );
    expect(screen.queryByText(/Désactiver le reranking/i)).not.toBeInTheDocument();
  });

  it("rend le dialog quand open=true", () => {
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/Désactiver le reranking/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Annuler/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Désactiver$/i })).toBeInTheDocument();
  });

  it("appelle useDeleteRerankConfig.mutate au clic sur Désactiver", async () => {
    deleteMutate.mockClear();
    const onOpenChange = vi.fn();
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={true} onOpenChange={onOpenChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Désactiver$/i }));
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledOnce());
  });
});
