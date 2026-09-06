import { Navigate, Route, Routes } from "react-router-dom";
import { ChunkingStrategiesPage } from "@/pages/ChunkingStrategiesPage";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import { ApiKeysPage } from "@/pages/ApiKeysPage";
import { HarpocrateVaultsPage } from "@/pages/HarpocrateVaultsPage";
import { McpSearchPage } from "@/pages/McpSearchPage";
import { ModelsPage } from "@/pages/ModelsPage";
import { PushActivityPage } from "@/pages/PushActivityPage";
import { OidcConfigPage } from "@/pages/OidcConfigPage";
import { ProcessingPage } from "@/pages/ProcessingPage";
import { EventsProducerPage } from "@/pages/EventsProducerPage";
import { IntegrationContractsPage } from "@/pages/IntegrationContractsPage";
import { PromptsPage } from "@/pages/PromptsPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { NotFound } from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="/workspaces" element={<WorkspacesPage />} />
      <Route path="/models" element={<ModelsPage />} />
      <Route path="/prompts" element={<PromptsPage />} />
      <Route path="/chunking-strategies" element={<ChunkingStrategiesPage />} />
      <Route path="/push" element={<PushActivityPage />} />
      <Route path="/mcp" element={<McpSearchPage />} />
      <Route path="/settings/profile" element={<ProfilePage />} />
      <Route path="/settings/api-keys" element={<ApiKeysPage />} />
      <Route path="/settings/harpocrate-vaults" element={<HarpocrateVaultsPage />} />
      <Route path="/settings/oidc-config" element={<OidcConfigPage />} />
      <Route path="/settings/processing" element={<ProcessingPage />} />
      <Route path="/settings/events-producer" element={<EventsProducerPage />} />
      <Route path="/integration/contracts" element={<IntegrationContractsPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
