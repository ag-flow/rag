import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import frPush from "@/i18n/fr/push.json";
import { LoadGatePanel } from "@/pages/push/LoadGatePanel";
import type { LoadGateStatus } from "@/lib/load-gate";

const setGateMutate = vi.fn();

vi.mock("@/hooks/useLoadGate", () => ({
  useLoadGate: vi.fn(),
  useSetLoadGate: () => ({ mutate: setGateMutate, isPending: false }),
}));
vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useLoadGate } from "@/hooks/useLoadGate";

function mockStatus(partial: Partial<LoadGateStatus>): void {
  vi.mocked(useLoadGate).mockReturnValue({
    data: {
      enabled: true,
      overloaded: false,
      cpu_psi_avg60: 5.2,
      memory_used_pct: 42.0,
      cpu_threshold_pct: 40,
      memory_threshold_pct: 85,
      reasons: [],
      ...partial,
    },
  } as unknown as ReturnType<typeof useLoadGate>);
}

const testI18n = i18next.createInstance();
await testI18n.use(initReactI18next).init({
  lng: "fr",
  fallbackLng: "fr",
  ns: ["push"],
  defaultNS: "push",
  resources: { fr: { push: frPush } },
  interpolation: { escapeValue: false },
});

function renderPanel() {
  return render(
    <I18nextProvider i18n={testI18n}>
      <LoadGatePanel />
    </I18nextProvider>,
  );
}

describe("LoadGatePanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("badge Normal + métriques et seuils affichés", () => {
    mockStatus({});
    renderPanel();
    expect(screen.getByText("Normal")).toBeInTheDocument();
    expect(screen.getByText(/5\.2 %.*seuil 40 %/)).toBeInTheDocument();
    expect(screen.getByText(/42 %.*seuil 85 %/)).toBeInTheDocument();
  });

  it("badge pause quand surchargé", () => {
    mockStatus({ overloaded: true, cpu_psi_avg60: 62.1, reasons: ["cpu psi avg60 62.1 > 40%"] });
    renderPanel();
    expect(screen.getByText("Jobs en pause (surcharge)")).toBeInTheDocument();
  });

  it("badge désactivé quand le gate est off", () => {
    mockStatus({ enabled: false, overloaded: false });
    renderPanel();
    expect(screen.getByText("Désactivé")).toBeInTheDocument();
  });

  it("enregistrer envoie les seuils saisis", () => {
    mockStatus({});
    renderPanel();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Seuil CPU (%)" }), {
      target: { value: "60" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(setGateMutate).toHaveBeenCalledWith(
      { enabled: true, cpu_threshold_pct: 60, memory_threshold_pct: 85 },
      expect.anything(),
    );
  });

  it("PSI indisponible affiché n/d", () => {
    mockStatus({ cpu_psi_avg60: null });
    renderPanel();
    expect(screen.getByText(/n\/d.*seuil 40 %/)).toBeInTheDocument();
  });
});
