import { Navigate, Route, Routes } from "react-router-dom";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import { NotFound } from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="/workspaces" element={<WorkspacesPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
