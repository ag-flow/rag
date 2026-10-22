import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "../workspace/__tests__/testUtils";
import { UsersPage } from "@/pages/UsersPage";
import { ApiError } from "@/lib/api";
import type { UserAccount } from "@/lib/users";

vi.mock("@/lib/users", () => ({ usersApi: { list: vi.fn(), setRole: vi.fn() } }));
const { toastSpy } = vi.hoisted(() => ({ toastSpy: vi.fn() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: toastSpy }) }));

import { usersApi } from "@/lib/users";

const list = vi.mocked(usersApi.list);
const setRole = vi.mocked(usersApi.setRole);

const user = (over: Partial<UserAccount>): UserAccount => ({
  id: "u1",
  username: "boot",
  email: "boot@example.com",
  role: "rag-admin",
  oidc_issuer: null,
  has_local_password: true,
  created_at: "2026-10-01T00:00:00Z",
  ...over,
});

describe("UsersPage", () => {
  beforeEach(() => {
    list.mockReset();
    setRole.mockReset();
    toastSpy.mockReset();
  });

  it("liste les comptes avec leur type et leur rôle", async () => {
    list.mockResolvedValue([
      user({}),
      user({
        id: "u2",
        username: "gael",
        email: "gael@example.com",
        role: "rag-viewer",
        oidc_issuer: "https://security.yoops.org/realms/yoops",
        has_local_password: false,
      }),
    ]);
    renderWithProviders(<UsersPage />);
    const row = (await screen.findByText("gael")).closest("tr") as HTMLElement;
    expect(within(row).getByText("OIDC")).toBeInTheDocument();
    expect(within(row).getByLabelText("Rôle de gael")).toHaveValue("rag-viewer");
    expect(screen.getByLabelText("Rôle de boot")).toHaveValue("rag-admin");
  });

  it("change le rôle, et « aucun accès » envoie null", async () => {
    list.mockResolvedValue([user({ id: "u2", username: "gael", role: "rag-viewer" })]);
    setRole.mockResolvedValue(user({ id: "u2", username: "gael", role: null }));
    renderWithProviders(<UsersPage />);
    fireEvent.change(await screen.findByLabelText("Rôle de gael"), {
      target: { value: "none" },
    });
    await waitFor(() => expect(setRole).toHaveBeenCalledWith("u2", null));
    expect(toastSpy).toHaveBeenCalledWith({ title: "Rôle de « gael » mis à jour." });
  });

  it("explique le refus de rétrograder le dernier administrateur", async () => {
    list.mockResolvedValue([user({})]);
    setRole.mockRejectedValue(new ApiError(409, { detail: "last_admin" }));
    renderWithProviders(<UsersPage />);
    fireEvent.change(await screen.findByLabelText("Rôle de boot"), {
      target: { value: "rag-viewer" },
    });
    await waitFor(() => expect(toastSpy).toHaveBeenCalledTimes(1));
    expect(toastSpy.mock.calls[0]?.[0].title).toMatch(/dernier administrateur/);
  });
});
