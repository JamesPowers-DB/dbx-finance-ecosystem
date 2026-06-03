import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production the FastAPI backend serves the built FE assets at the same origin.
// In dev (vite on :5173) we proxy /api → http://localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
