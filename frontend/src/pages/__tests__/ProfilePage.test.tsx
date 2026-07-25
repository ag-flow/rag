import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../workspace/__tests__/testUtils";
import { ProfilePage } from "@/pages/ProfilePage";

vi.mock("@/lib/profile", () => ({
  profileApi: { get: vi.fn(), update: vi.fn(), generateIdentity: vi.fn() },
}));

import { profileApi } from "@/lib/profile";

const getProfile = vi.mocked(profileApi.get);
const updateProfile = vi.mocked(profileApi.update);
const generateIdentity = vi.mocked(profileApi.generateIdentity);

describe("ProfilePage", () => {
  beforeEach(() => {
    getProfile.mockReset();
    updateProfile.mockReset();
    generateIdentity.mockReset();
    getProfile.mockResolvedValue({
      username: "gael",
      email: "gael@corp.example",
      identity: null,
    });
  });

  it("affiche le profil : username, email, GUID vide", async () => {
    renderWithProviders(<ProfilePage />);
    expect(await screen.findByText("gael")).toBeInTheDocument();
    expect(screen.getByDisplayValue("gael@corp.example")).toBeInTheDocument();
  });

  it("génère un GUID et le pose dans le champ", async () => {
    generateIdentity.mockResolvedValue({ identity: "abc-123-def" });
    renderWithProviders(<ProfilePage />);
    await screen.findByText("gael");

    fireEvent.click(screen.getByRole("button", { name: /Générer/ }));
    await waitFor(() => {
      expect(screen.getByDisplayValue("abc-123-def")).toBeInTheDocument();
    });
    // Non persisté tant qu'on n'enregistre pas.
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it("enregistre email + GUID via PUT", async () => {
    updateProfile.mockResolvedValue({
      username: "gael",
      email: "gael@corp.example",
      identity: "my-guid",
    });
    renderWithProviders(<ProfilePage />);
    await screen.findByText("gael");

    fireEvent.change(screen.getByPlaceholderText(/0f8fad5b/), {
      target: { value: "my-guid" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => {
      expect(updateProfile).toHaveBeenCalledWith({
        email: "gael@corp.example",
        identity: "my-guid",
      });
    });
  });

  it("avertit quand l'email change (bascule d'owner)", async () => {
    renderWithProviders(<ProfilePage />);
    await screen.findByText("gael");

    fireEvent.change(screen.getByDisplayValue("gael@corp.example"), {
      target: { value: "autre@corp.example" },
    });
    expect(
      screen.getByText(/Changer d'email change la clé de possession/),
    ).toBeInTheDocument();
  });
});
