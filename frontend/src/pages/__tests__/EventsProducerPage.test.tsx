import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frEventsProducer from "@/i18n/fr/events_producer.json";
import enEventsProducer from "@/i18n/en/events_producer.json";
import { ApiError } from "@/lib/api";
import type { EventsProducerConfig } from "@/lib/events-producer.types";
import { EventsProducerPage } from "@/pages/EventsProducerPage";

const saveMutate = vi.fn();
const testMutate = vi.fn();

vi.mock("@/hooks/useEventsProducer", () => ({
  useEventsProducerConfig: vi.fn(),
  useSaveEventsProducer: () => ({ mutate: saveMutate, isPending: false }),
  useTestEventsProducerConnection: () => ({ mutate: testMutate, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useEventsProducerConfig } from "@/hooks/useEventsProducer";

const baseConfig: EventsProducerConfig = {
  enabled: true,
  workflow_base_url: "https://workflow.example.com/ingest",
  source_id: "src-guid-1",
  secret_ref: "${vault://rag:workflow-hmac}",
  source_uri: "urn:yoops:rag",
  events: [],
  known_events: ["rag.workspace.created.v1"],
};

function mockConfig(data: EventsProducerConfig | undefined): void {
  vi.mocked(useEventsProducerConfig).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useEventsProducerConfig>);
}

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["events_producer"],
    defaultNS: "events_producer",
    resources: {
      fr: { events_producer: frEventsProducer },
      en: { events_producer: enEventsProducer },
    },
    interpolation: { escapeValue: false },
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <EventsProducerPage />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("EventsProducerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfig(baseConfig);
  });

  it("charge la config et affiche les champs + events émissibles", () => {
    renderPage();
    expect(screen.getByDisplayValue("https://workflow.example.com/ingest")).toBeInTheDocument();
    expect(screen.getByDisplayValue("src-guid-1")).toBeInTheDocument();
    expect(screen.getByLabelText("rag.workspace.created.v1")).toBeInTheDocument();
  });

  it("coche un event et enregistre avec le bon body", async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText("rag.workspace.created.v1"));
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/ }));
    await waitFor(() => expect(saveMutate).toHaveBeenCalled());
    expect(saveMutate.mock.calls[0]?.[0]).toEqual({
      enabled: true,
      workflow_base_url: "https://workflow.example.com/ingest",
      source_id: "src-guid-1",
      secret_ref: "${vault://rag:workflow-hmac}",
      source_uri: "urn:yoops:rag",
      events: ["rag.workspace.created.v1"],
    });
  });

  it("affiche le résultat du test de connexion", () => {
    testMutate.mockImplementation((_v: unknown, opts: { onSuccess: (r: unknown) => void }) => {
      opts.onSuccess({ ok: true, status_code: 200, detail: "pong" });
    });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Tester la connexion/ }));
    expect(screen.getByText(/Connexion réussie \(HTTP 200\)/)).toBeInTheDocument();
  });

  it("affiche l'échec test avec status_code et detail", () => {
    testMutate.mockImplementation((_v: unknown, opts: { onSuccess: (r: unknown) => void }) => {
      opts.onSuccess({ ok: false, status_code: 502, detail: "bad gateway" });
    });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Tester la connexion/ }));
    expect(screen.getByText(/Échec \(HTTP 502\) : bad gateway/)).toBeInTheDocument();
  });

  it("affiche le message producer_not_configured", () => {
    testMutate.mockImplementation((_v: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError(new ApiError(422, { detail: { error: "producer_not_configured" } }));
    });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Tester la connexion/ }));
    expect(screen.getByText(/Configure d'abord l'URL/)).toBeInTheDocument();
  });

  it("affiche inline les unknown_events sur 422 à l'enregistrement", () => {
    saveMutate.mockImplementation((_p: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError(
        new ApiError(422, { detail: { error: "unknown_events", events: ["rag.foo.v1"] } }),
      );
    });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/ }));
    expect(screen.getByText(/rag\.foo\.v1/)).toBeInTheDocument();
  });
});
