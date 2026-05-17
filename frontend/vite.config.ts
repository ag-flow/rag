import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Défaut localhost — ne JAMAIS pointer par défaut sur un LXC partagé (ex 303)
// pour éviter qu'un `npm run dev` sans VITE_BACKEND_URL ne tape sur l'env d'un
// autre utilisateur. Si pas de backend local en :8000, le proxy Vite échoue
// gracieusement (ECONNREFUSED) au lieu de polluer un autre env.
const BACKEND = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api":  { target: BACKEND, changeOrigin: true },
      "/auth": { target: BACKEND, changeOrigin: true },
      "/me":   { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
