import { api } from "@/lib/api";
import type {
  LlmConfig,
  LlmConfigCreate,
  LlmConfigPatch,
  PlaygroundChatRequest,
  PlaygroundChatResponse,
} from "@/lib/playground.types";

const BASE = (name: string) => `/api/admin/workspaces/${name}/llm-configs`;

export const playgroundApi = {
  listConfigs: (workspaceName: string) =>
    api.get<LlmConfig[]>(BASE(workspaceName)),

  createConfig: (workspaceName: string, payload: LlmConfigCreate) =>
    api.post<LlmConfig>(BASE(workspaceName), payload),

  patchConfig: (workspaceName: string, configId: string, payload: LlmConfigPatch) =>
    api.patch<LlmConfig>(`${BASE(workspaceName)}/${configId}`, payload),

  deleteConfig: (workspaceName: string, configId: string) =>
    api.delete<void>(`${BASE(workspaceName)}/${configId}`),

  chat: (workspaceName: string, payload: PlaygroundChatRequest) =>
    api.post<PlaygroundChatResponse>(
      `/api/workspaces/${workspaceName}/playground/chat`,
      payload,
    ),
};
