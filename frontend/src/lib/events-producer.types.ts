// Miroir des schemas backend du producteur d'events (Porte A rag -> workflow).
// `EventsProducerConfig` = réponse GET/PUT ; `EventsProducerSpec` = body PUT.

export interface EventsProducerConfig {
  enabled: boolean;
  workflow_base_url: string;
  source_id: string;
  secret_ref: string;
  source_uri: string;
  events: string[];
  known_events: string[];
}

export interface EventsProducerSpec {
  enabled: boolean;
  workflow_base_url: string;
  source_id: string;
  secret_ref: string;
  source_uri: string;
  events: string[];
}

export interface TestConnectionResult {
  ok: boolean;
  status_code: number;
  detail: string;
}
