import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

const BACKEND = process.env.VITE_BACKEND_URL ?? "http://192.168.10.184:8000";

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
