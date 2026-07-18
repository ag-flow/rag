import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { PlaygroundChunkPreviewTab } from "@/pages/workspace/PlaygroundChunkPreviewTab";
import { usePreviewChunking } from "@/hooks/useChunkingStrategies";
import type { PreviewResult } from "@/lib/chunking-strategies.types";

const emptyMutation = {
  mutate: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  error: null,
  data: undefined,
};

vi.mock("@/hooks/useChunkingStrategies", () => ({
  useChunkingStrategies: vi.fn(() => ({
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
        used_by_categories: 0,
        created_at: "",
        updated_at: "",
      },
    ],
    isLoading: false,
  })),
  usePreviewChunking: vi.fn(() => emptyMutation),
  useCompareChunking: vi.fn(() => emptyMutation),
}));

function previewResult(): PreviewResult {
  return {
    strategy: {
      id: "00000000-0000-0000-0000-000000000001",
      label: "markdown-deep",
      slug: "markdown-deep",
      algo: "prose",
      parser_slug: "markdown",
    },
    parents: [{ section_key: "Guide", chars: 120 }],
    chunks: [
      {
        index: 0,
        embed_text: "Guide\n\nContenu du chunk",
        tokens: 42,
        chunk_hash: "abc",
        parent_key: "Guide",
        region_type: "code_fence",
        region_qualifier: "mermaid",
      },
    ],
    regions: [
      {
        region_type: "code_fence",
        qualifier: "mermaid",
        start_line: 5,
        end_line: 9,
        routed: true,
        atomic: false,
        overflow_policy: "parent_only",
        target_strategy_id: null,
      },
    ],
    total_chunks: 1,
    total_tokens: 42,
  };
}

describe("PlaygroundChunkPreviewTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("désactive le bouton sans stratégie ni contenu", () => {
    renderWithProviders(<PlaygroundChunkPreviewTab workspaceName="ws" />);
    expect(screen.getByRole("button", { name: "Prévisualiser" })).toBeDisabled();
  });

  it("affiche le résultat de preview avec totaux et badge de région", () => {
    vi.mocked(usePreviewChunking).mockReturnValue({
      ...emptyMutation,
      data: previewResult(),
    } as unknown as ReturnType<typeof usePreviewChunking>);

    renderWithProviders(<PlaygroundChunkPreviewTab workspaceName="ws" />);

    expect(screen.getByText(/1 chunks · ~42 tokens/)).toBeInTheDocument();
    expect(screen.getAllByText("code_fence:mermaid").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/1 région\(s\) détectée\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/parent_only — restituée au LLM/)).toBeInTheDocument();
    expect(screen.getByText(/Contenu du chunk/)).toBeInTheDocument();
  });
});
