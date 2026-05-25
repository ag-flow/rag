import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frModels from "@/i18n/fr/models.json";
import enModels from "@/i18n/en/models.json";

import { DeleteModelAlert } from "@/pages/models/DeleteModelAlert";

const mutateMock = vi.fn();

vi.mock("@/hooks/useModels", () => ({
  useDeleteModel: () => ({ mutate: mutateMock, isPending: false }),
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

function renderAlert(entry: { provider: string; model: string } | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <DeleteModelAlert entry={entry} onClose={() => {}} />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("DeleteModelAlert", () => {
  it("fermé si entry=null", () => {
    renderAlert(null);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("confirm déclenche useDeleteModel.mutate avec l'entry", () => {
    mutateMock.mockClear();
    renderAlert({ provider: "openai", model: "text-embedding-3-small" });
    // The alert dialog is open — click the "Supprimer" confirm button
    fireEvent.click(screen.getByText(/^Supprimer$/i));
    expect(mutateMock).toHaveBeenCalledWith(
      { provider: "openai", model: "text-embedding-3-small" },
      expect.anything(),
    );
  });
});
