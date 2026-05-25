import { Route, Routes } from "react-router-dom";
import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Toaster } from "@/components/ui/toaster";
import { AppRoutes } from "@/routes";
import { LoginPage } from "@/pages/LoginPage";

function GuardedShell() {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-slate-50">
        <Sidebar />
        <div className="flex-1 flex flex-col">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <AppRoutes />
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}

function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<GuardedShell />} />
      </Routes>
      <Toaster />
    </>
  );
}

export default App;
