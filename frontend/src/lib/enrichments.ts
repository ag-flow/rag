import { api } from "@/lib/api";
import type {
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplatePatch,
  Trigger,
  TriggerCreate,
  TriggerPatch,
  TriggerPrompt,
  TriggerPromptCreate,
} from "@/lib/enrichments.types";

export const enrichmentsApi = {
  listPrompts: () => api.get<PromptTemplate[]>("/api/admin/prompts"),

  createPrompt: (payload: PromptTemplateCreate) =>
    api.post<PromptTemplate>("/api/admin/prompts", payload),

  patchPrompt: (id: string, payload: PromptTemplatePatch) =>
    api.patch<PromptTemplate>(`/api/admin/prompts/${id}`, payload),

  deletePrompt: (id: string) => api.delete<void>(`/api/admin/prompts/${id}`),

  listTriggers: (workspaceName: string) =>
    api.get<Trigger[]>(`/api/admin/workspaces/${workspaceName}/triggers`),

  createTrigger: (workspaceName: string, payload: TriggerCreate) =>
    api.post<Trigger>(`/api/admin/workspaces/${workspaceName}/triggers`, payload),

  patchTrigger: (workspaceName: string, triggerId: string, payload: TriggerPatch) =>
    api.patch<Trigger>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}`,
      payload,
    ),

  deleteTrigger: (workspaceName: string, triggerId: string) =>
    api.delete<void>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}`,
    ),

  listTriggerPrompts: (workspaceName: string, triggerId: string) =>
    api.get<TriggerPrompt[]>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts`,
    ),

  createTriggerPrompt: (
    workspaceName: string,
    triggerId: string,
    payload: TriggerPromptCreate,
  ) =>
    api.post<TriggerPrompt>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts`,
      payload,
    ),

  deleteTriggerPrompt: (
    workspaceName: string,
    triggerId: string,
    promptId: string,
  ) =>
    api.delete<void>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts/${promptId}`,
    ),
};
