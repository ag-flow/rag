import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frProcessing from "@/i18n/fr/processing.json";
import { WorkerSlotsPanel } from "@/pages/processing/WorkerSlotsPanel";
import type { ProcessingStatus } from "@/lib/processing";

const setProcessingMutate = vi.fn();

vi.mock("@/hooks/useProcessing", () => ({
  useProcessing: vi.fn(),
  useSetProcessing: () => ({ mutate: setProcessingMutate, isPending: false }),
}));
vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useProcessing } from "@/hooks/useProcessing";

function mockStatus(partial: Partial<ProcessingStatus>): void {
  vi.mocked(useProcessing).mockReturnValue({
    data: {
      max_parallel_jobs: 2,
      active_jobs: 1,
      ...partial,
    },
  } as unknown as ReturnType<typeof useProcessing>);
}

const testI18n = i18next.createInstance();
await testI18n.use(initReactI18next).init({
  lng: "fr",
  fallbackLng: "fr",
  ns: ["processing"],
  defaultNS: "processing",
  resources: { fr: { processing: frProcessing } },
  interpolation: { escapeValue: false },
});

function renderPanel() {
  return render(
    <I18nextProvider i18n={testI18n}>
      <WorkerSlotsPanel />
    </I18nextProvider>,
  );
}

describe("WorkerSlotsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("affiche le plafond courant et l'occupation", () => {
    mockStatus({ max_parallel_jobs: 3, active_jobs: 2 });
    renderPanel();
    expect(screen.getByRole("spinbutton", { name: "Jobs simultanés max" })).toHaveValue(3);
    expect(screen.getByText("En cours : 2")).toBeInTheDocument();
  });

  it("enregistrer envoie le plafond saisi", () => {
    mockStatus({});
    renderPanel();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Jobs simultanés max" }), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(setProcessingMutate).toHaveBeenCalledWith({ max_parallel_jobs: 4 }, expect.anything());
  });

  it("valeur invalide retombe sur le plafond courant", () => {
    mockStatus({ max_parallel_jobs: 5 });
    renderPanel();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Jobs simultanés max" }), {
      target: { value: "999" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(setProcessingMutate).toHaveBeenCalledWith({ max_parallel_jobs: 5 }, expect.anything());
  });
});
