import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  eventsProducerApi,
  isProducerNotConfigured,
  unknownEventsFromError,
} from "@/lib/events-producer";
import { api } from "@/lib/api";
import type {
  EventsProducerConfig,
  EventsProducerSpec,
  TestConnectionResult,
} from "@/lib/events-producer.types";

const config: EventsProducerConfig = {
  enabled: true,
  workflow_base_url: "https://workflow.example.com/ingest",
  source_id: "00000000-0000-0000-0000-000000000001",
  secret_ref: "${vault://rag:workflow-hmac}",
  source_uri: "urn:yoops:rag",
  events: ["rag.workspace.created.v1"],
  known_events: ["rag.workspace.created.v1"],
};

const spec: EventsProducerSpec = {
  enabled: true,
  workflow_base_url: config.workflow_base_url,
  source_id: config.source_id,
  secret_ref: config.secret_ref,
  source_uri: config.source_uri,
  events: config.events,
};

describe("eventsProducerApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("get appelle GET /api/admin/events-producer", async () => {
    const spy = vi.spyOn(api, "get").mockResolvedValue(config);
    await expect(eventsProducerApi.get()).resolves.toEqual(config);
    expect(spy).toHaveBeenCalledWith("/api/admin/events-producer");
  });

  it("save appelle PUT avec le spec", async () => {
    const spy = vi.spyOn(api, "put").mockResolvedValue(config);
    await eventsProducerApi.save(spec);
    expect(spy).toHaveBeenCalledWith("/api/admin/events-producer", spec);
  });

  it("testConnection appelle POST test-connection", async () => {
    const result: TestConnectionResult = { ok: true, status_code: 200, detail: "pong" };
    const spy = vi.spyOn(api, "post").mockResolvedValue(result);
    await expect(eventsProducerApi.testConnection()).resolves.toEqual(result);
    expect(spy).toHaveBeenCalledWith("/api/admin/events-producer/test-connection", {});
  });
});

describe("unknownEventsFromError", () => {
  it("extrait les events refusés du shape 422", () => {
    expect(
      unknownEventsFromError({ detail: { error: "unknown_events", events: ["rag.bad.v1"] } }),
    ).toEqual(["rag.bad.v1"]);
  });

  it("retourne null sur un autre code d'erreur", () => {
    expect(unknownEventsFromError({ detail: { error: "producer_not_configured" } })).toBeNull();
  });

  it("retourne null sur un detail string ou non-objet", () => {
    expect(unknownEventsFromError({ detail: "validation error" })).toBeNull();
    expect(unknownEventsFromError(null)).toBeNull();
  });
});

describe("isProducerNotConfigured", () => {
  it("vrai sur le shape 422 producer_not_configured", () => {
    expect(isProducerNotConfigured({ detail: { error: "producer_not_configured" } })).toBe(true);
  });

  it("faux sinon", () => {
    expect(isProducerNotConfigured({ detail: { error: "unknown_events", events: [] } })).toBe(false);
    expect(isProducerNotConfigured({ detail: "boom" })).toBe(false);
    expect(isProducerNotConfigured(null)).toBe(false);
  });
});
