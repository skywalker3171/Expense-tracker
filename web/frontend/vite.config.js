import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During dev, proxy /api to the FastAPI backend on :8000.
// In production the built assets are served by FastAPI, so same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});