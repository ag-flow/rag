import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { WorkspaceCreateDialog } from "@/pages/WorkspaceCreateDialog";
import * as apiModule from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("WorkspaceCreateDialog", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("renders form fields when open", () => {
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Name input — FormLabel htmlFor wired via FormItem id
    expect(screen.getByPlaceholderText("harpocrate")).toBeInTheDocument();
    // Provider and model selects rendered as combobox buttons
    const comboboxes = screen.getAllByRole("combobox");
    expect(comboboxes.length).toBeGreaterThanOrEqual(2);
    // api_key_ref present by default (provider = openai)
    expect(screen.getByPlaceholderText("openai_embedding_key")).toBeInTheDocument();
  });

  it("shows base_url field only for ollama provider, not api_key_ref", () => {
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Initially openai → api_key_ref visible, base_url not
    expect(screen.getByPlaceholderText("openai_embedding_key")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("http://192.168.10.80:11434")).not.toBeInTheDocument();

    // Simulate provider change to ollama via the hidden select input
    // Radix Select renders a native <select> in the DOM for form compatibility
    const nativeSelects = document.querySelectorAll("select");
    // First native select is provider
    const providerSelect = nativeSelects[0];
    expect(providerSelect).toBeDefined();
    fireEvent.change(providerSelect!, { target: { value: "ollama" } });

    // After switching to ollama → base_url visible, api_key_ref gone
    expect(screen.getByPlaceholderText("http://192.168.10.80:11434")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("openai_embedding_key")).not.toBeInTheDocument();
  });

  it("submits valid form and calls api.post", async () => {
    const postSpy = vi
      .spyOn(apiModule.api, "post")
      .mockResolvedValue({ name: "test_ws", api_key: "key" });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={onOpenChange} />
      </Wrapper>,
    );

    await user.type(screen.getByPlaceholderText("harpocrate"), "test_ws");
    await user.type(screen.getByPlaceholderText("openai_embedding_key"), "openai_key");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        "/api/admin/workspaces",
        expect.objectContaining({
          name: "test_ws",
          indexer: expect.objectContaining({
            provider: "openai",
            api_key_ref: "openai_key",
          }),
        }),
      );
    });
  });

  it("validates name format (lowercase only)", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    await user.type(screen.getByPlaceholderText("harpocrate"), "BadName");
    await user.type(screen.getByPlaceholderText("openai_embedding_key"), "key");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      expect(screen.getByText(/name_invalid_format/i)).toBeInTheDocument();
    });
  });
});
