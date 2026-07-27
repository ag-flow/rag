import { api } from "@/lib/api";
import type {
  EventsProducerConfig,
  EventsProducerSpec,
  TestConnectionResult,
} from "@/lib/events-producer.types";

const BASE = "/api/admin/events-producer";

export const eventsProducerApi = {
  get: () => api.get<EventsProducerConfig>(BASE),
  save: (payload: EventsProducerSpec) => api.put<EventsProducerConfig>(BASE, payload),
  testConnection: () => api.post<TestConnectionResult>(`${BASE}/test-connection`, {}),
};

function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail !== "object" || detail === null || !("error" in detail)) {
    return null;
  }
  const code = (detail as Record<string, unknown>).error;
  return typeof code === "string" ? code : null;
}

/**
 * Extrait la liste des events refusés d'une 422 `unknown_events`.
 * Retourne `null` si le body ne correspond pas à ce contrat.
 */
export function unknownEventsFromError(body: unknown): string[] | null {
  if (errorCode(body) !== "unknown_events") {
    return null;
  }
  const detail = (body as { detail: Record<string, unknown> }).detail;
  const events = detail.events;
  if (!Array.isArray(events)) {
    return null;
  }
  return events.filter((e): e is string => typeof e === "string");
}

/** Vrai si le body est une 422 `producer_not_configured` (test-connection). */
export function isProducerNotConfigured(body: unknown): boolean {
  return errorCode(body) === "producer_not_configured";
}
