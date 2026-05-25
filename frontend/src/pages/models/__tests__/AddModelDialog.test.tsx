import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frModels from "@/i18n/fr/models.json";
import enModels from "@/i18n/en/models.json";

import { AddModelDialog } from "@/pages/models/AddModelDialog";

const mutateMock = vi.fn();

vi.mock("@/hooks/useModels", () => ({
  useCreateModel: () => ({ mutate: mutateMock, isPending: false }),
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

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <AddModelDialog open onOpenChange={() => {}} />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("AddModelDialog", () => {
  it("le champ provider personnalisé n'apparaît pas à l'état initial (openai sélectionné)", () => {
    renderDialog();
    // Initialement, provider = openai → pas de champ "Provider personnalisé"
    expect(screen.queryByPlaceholderText("mistral")).not.toBeInTheDocument();
  });

  it("submit avec valeurs valides appelle create.mutate", () => {
    mutateMock.mockClear();
    renderDialog();
    fireEvent.change(screen.getByPlaceholderText("text-embedding-3-small"), {
      target: { value: "test-model" },
    });
    fireEvent.change(screen.getByDisplayValue("1"), { target: { value: "1024" } });
    fireEvent.click(screen.getByText(/^Ajouter$/i));
    // mutate est appelé async via react-hook-form — attendre.
    return new Promise<void>((resolve) =>
      setTimeout(() => {
        expect(mutateMock).toHaveBeenCalled();
        resolve();
      }, 100),
    );
  });
});
