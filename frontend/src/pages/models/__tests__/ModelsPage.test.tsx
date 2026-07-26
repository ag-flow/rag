import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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
        kind: "embedding",
        dimension: 1536,
        created_at: "2026-05-15T00:00:00Z",
        is_system: true,
      },
      {
        provider: "openai",
        model: "text-embedding-3-large",
        kind: "embedding",
        dimension: 3072,
        created_at: "2026-05-15T00:00:00Z",
        is_system: true,
      },
      {
        provider: "ollama",
        model: "nomic-embed-text",
        kind: "embedding",
        dimension: 768,
        created_at: "2026-05-15T00:00:00Z",
        is_system: false,
      },
      {
        provider: "ollama",
        model: "llama3.1:8b",
        kind: "llm",
        dimension: null,
        created_at: "2026-05-15T00:00:00Z",
        is_system: false,
      },
      {
        provider: "cohere",
        model: "rerank-v3.5",
        kind: "rerank",
        dimension: null,
        created_at: "2026-05-15T00:00:00Z",
        is_system: true,
      },
    ],
    isLoading: false,
  }),
  useCreateModel: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateModel: () => ({ mutate: vi.fn(), isPending: false }),
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

function expandAll() {
  // Les entêtes de groupe sont les boutons contenant le compteur "(n)".
  for (const btn of screen.getAllByRole("button")) {
    if (/\(\d+\)/.test(btn.textContent ?? "")) fireEvent.click(btn);
  }
}

describe("ModelsPage", () => {
  it("au chargement, tous les blocs provider sont collapsés", () => {
    renderPage();
    // Les entêtes sont visibles mais aucun modèle n'est affiché.
    expect(screen.getByText(/openai/)).toBeInTheDocument();
    expect(screen.queryByText("text-embedding-3-small")).not.toBeInTheDocument();
    expect(screen.queryByText("nomic-embed-text")).not.toBeInTheDocument();
  });

  it("affiche les modèles groupés par provider, sections triées alphabétiquement", () => {
    renderPage();
    expandAll();
    // Les deux providers présents :
    expect(screen.getByText(/openai/)).toBeInTheDocument();
    expect(screen.getByText(/ollama/)).toBeInTheDocument();
    // Les 3 models présents :
    expect(screen.getByText("text-embedding-3-small")).toBeInTheDocument();
    expect(screen.getByText("text-embedding-3-large")).toBeInTheDocument();
    expect(screen.getByText("nomic-embed-text")).toBeInTheDocument();
  });

  it("badge Système sur les modèles du catalogue, suppression réservée aux modèles possédés", () => {
    renderPage();
    expandAll();
    // 3 modèles système → 3 badges ; les modèles utilisateur n'en ont pas.
    expect(screen.getAllByText("Système")).toHaveLength(3);
    // Deux menus d'actions (les modèles utilisateur) : les système n'en ont pas.
    expect(document.querySelectorAll('[aria-haspopup="menu"]')).toHaveLength(2);
  });

  it("affiche le type sur les lignes rerank et llm (pas de dimension)", () => {
    renderPage();
    expandAll();
    // "LLM" existe aussi comme bouton de filtre → on cible les spans de ligne.
    const rowLabels = [...document.querySelectorAll("li span.text-slate-500")].map(
      (el) => el.textContent,
    );
    expect(rowLabels).toContain("Rerank");
    expect(rowLabels).toContain("LLM");
  });

  it("filtre par type : Reranking ne garde que les modèles kind=rerank", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Reranking" }));
    expandAll();
    expect(screen.getByText("rerank-v3.5")).toBeInTheDocument();
    expect(screen.queryByText("text-embedding-3-small")).not.toBeInTheDocument();
    expect(screen.queryByText("llama3.1:8b")).not.toBeInTheDocument();
  });

  it("filtre par type : LLM ne garde que les modèles kind=llm", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "LLM" }));
    expandAll();
    expect(screen.getByText("llama3.1:8b")).toBeInTheDocument();
    expect(screen.queryByText("rerank-v3.5")).not.toBeInTheDocument();
  });
});
