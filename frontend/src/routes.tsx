import { Navigate, Route, Routes } from "react-router-dom";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import { HarpocrateVaultsPage } from "@/pages/HarpocrateVaultsPage";
import { ModelsPage } from "@/pages/ModelsPage";
import { OidcConfigPage } from "@/pages/OidcConfigPage";
import { PromptsPage } from "@/pages/PromptsPage";
import { NotFound } from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="/workspaces" element={<WorkspacesPage />} />
      <Route path="/models" element={<ModelsPage />} />
      <Route path="/prompts" element={<PromptsPage />} />
      <Route path="/settings/harpocrate-vaults" element={<HarpocrateVaultsPage />} />
      <Route path="/settings/oidc-config" element={<OidcConfigPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
