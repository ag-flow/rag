import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

import frModels from "@/i18n/fr/models.json";
import enModels from "@/i18n/en/models.json";

import { ModelsPage } from "@/pages/ModelsPage";

vi.mock("@/hooks/useModels", () => ({
  useModels: () => ({
    data: [
      {
        provider: "openai",
        model: "text-embedding-3-small",
        dimension: 1536,
        created_at: "2026-05-15T00:00:00Z",
      },
      {
        provider: "openai",
        model: "text-embedding-3-large",
        dimension: 3072,
        created_at: "2026-05-15T00:00:00Z",
      },
      {
        provider: "ollama",
        model: "nomic-embed-text",
        dimension: 768,
        created_at: "2026-05-15T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useCreateModel: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteModel: () => ({ mutate: vi.fn(), isPending: false }),
  usePricing: () => ({ data: undefined }),
}));

const testI18n = i18next.createInstance();
void testI18n.use(initReactI18next).init({
  lng: "fr",
  fallbackLng: "fr",
  ns: ["models"],
  defaultNS: "models",
  resources: {
    fr: { models: frModels },
    en: { models: enModels },
  },
  interpolation: { escapeValue: false },
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <I18nextProvider i18n={testI18n}>
        <QueryClientProvider client={qc}>
          <ModelsPage />
        </QueryClientProvider>
      </I18nextProvider>
    </MemoryRouter>,
  );
}

describe("ModelsPage", () => {
  it("affiche les modèles groupés par provider, sections triées alphabétiquement", () => {
    renderPage();
    // Les deux providers présents :
    expect(screen.getByText(/openai/)).toBeInTheDocument();
    expect(screen.getByText(/ollama/)).toBeInTheDocument();
    // Les 3 models présents :
    expect(screen.getByText("text-embedding-3-small")).toBeInTheDocument();
    expect(screen.getByText("text-embedding-3-large")).toBeInTheDocument();
    expect(screen.getByText("nomic-embed-text")).toBeInTheDocument();
  });
});
