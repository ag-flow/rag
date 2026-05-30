export type PromptTemplate = {
  id: string;
  name: string;
  language: string;
  description: string | null;
  metadata_key: string;
  result_type: "text" | "json";
  result_schema: object | null;
  prompt: string;
  created_at: string;
  updated_at: string;
};

export type PromptTemplateCreate = {
  name: string;
  language: string;
  description?: string | null;
  metadata_key: string;
  result_type: "text" | "json";
  result_schema?: object | null;
  prompt: string;
};

export type PromptTemplatePatch = {
  description?: string | null;
  prompt?: string;
  result_schema?: object | null;
};

export type Trigger = {
  id: string;
  extension: string;
  enabled: boolean;
  created_at: string;
};

export type TriggerCreate = {
  extension: string;
  enabled?: boolean;
};

export type TriggerPatch = {
  enabled: boolean;
};

export type TriggerPrompt = {
  id: string;
  template_id: string;
  template_name: string;
  llm_id: string;
  llm_provider: string;
  llm_model: string;
  order_index: number;
  enabled: boolean;
};

export type TriggerPromptCreate = {
  template_id: string;
  llm_id: string;
  order_index: number;
  enabled?: boolean;
};
