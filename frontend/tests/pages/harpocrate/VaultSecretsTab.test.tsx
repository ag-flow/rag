import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { VaultSecretsTab } from "@/pages/harpocrate/VaultSecretsTab";
import * as apiModule from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const sampleSecretsResponse = {
  secrets: [
    {
      id: "s-1",
      name: "openai_embedding_key",
      description: "Used by indexer",
      is_placeholder: false,
      tags: ["model"],
    },
    {
      id: "s-2",
      name: "voyage_api_key",
      description: null,
      is_placeholder: true,
      tags: [],
    },
  ],
  next_cursor: null,
};

describe("VaultSecretsTab", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("renders the secrets table with names and badges", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue(sampleSecretsResponse);

    render(
      <Wrapper>
        <VaultSecretsTab vaultId="v-1" />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText("openai_embedding_key")).toBeInTheDocument();
      expect(screen.getByText("voyage_api_key")).toBeInTheDocument();
      // One badge per row (secret vs placeholder).
      expect(screen.getByText(/^secret$/i)).toBeInTheDocument();
      expect(screen.getByText(/^placeholder$/i)).toBeInTheDocument();
    });
  });

  it("passes the path filter as a query string param to the API", async () => {
    const getSpy = vi
      .spyOn(apiModule.api, "get")
      .mockResolvedValue(sampleSecretsResponse);
    const user = userEvent.setup();

    render(
      <Wrapper>
        <VaultSecretsTab vaultId="v-1" />
      </Wrapper>,
    );

    await waitFor(() => expect(getSpy).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText("path/"), "models/");

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        expect.stringContaining("path=models"),
      );
    });
  });

  it("copies the secret name to clipboard when Copier is clicked", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue(sampleSecretsResponse);
    const writeText = vi.fn().mockResolvedValue(undefined);
    // userEvent.setup() installs its own clipboard stub via defineProperty,
    // so we must override AFTER setup() to expose our spy to the component.
    const user = userEvent.setup();
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });

    render(
      <Wrapper>
        <VaultSecretsTab vaultId="v-1" />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText("openai_embedding_key")).toBeInTheDocument();
    });

    // The Copy button uses an aria-label "Copier le nom du secret" so the
    // accessible name is that label (not the inner "Copier" text).
    const copyButtons = screen.getAllByRole("button", {
      name: /copier le nom du secret/i,
    });
    await user.click(copyButtons[0]!);

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("openai_embedding_key");
    });
  });
});
